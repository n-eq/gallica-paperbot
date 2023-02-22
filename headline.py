#!/usr/bin/env python

import os, sys, re
import dbm.ndbm
import urllib.request, urllib.parse, urllib.error, urllib.request, urllib.error, urllib.parse
import datetime, requests

from lxml import etree

import logging
from logging.handlers import TimedRotatingFileHandler

import twitter
import config

logger = None

def init_logger(dry_run = False):
    global logger

    logger = logging.getLogger("gallica-headline")
    logger.setLevel(logging.DEBUG)

    if dry_run:
        handler = logging.StreamHandler(sys.stdout)
    else:
        handler = TimedRotatingFileHandler(config.logfile,
                                           utc=True, 
                                           when="d",
                                           interval=7, # rotate every week (7d)
                                           backupCount=31)
    handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] %(message)s'))
    logger.addHandler(handler)

def main(argv):
    global logger
    dry_run = False
    if len(argv) > 1: # for testing
        date = datetime.datetime.strptime(argv[1], '%Y/%m/%d')
        if (len(argv) > 2 and argv[2] == "--dryrun"):
            dry_run = True
    else:
        today = datetime.date.today()
        date = datetime.date(today.year-100, today.month, today.day)

    init_logger(dry_run)
    logger.info("Running script for %s" % date.strftime("%m/%d/%Y"))

    records = get_records(date)

    headlines = []
    for r in records:
        headlines.extend(blocks(r))

    headlines.sort(key=cmp_block)
    headlines.reverse()
    logger.info("Sorted headlines: ")
    for h in headlines[:10]:
        logger.info("[%d] %s, %s %s" % (cmp_block(h), h['text'].encode('utf-8'), h['paper'], h['url']))

    if (len(headlines) > 0):
        h = headlines[0]
        
        f = get_frontpage(h, date)
        h['front_page'] = f

        msg = format_status(h, date)
        twitter.tweet(msg, logger, dry_run, f)
    else:
        logger.error("No headlines found.")

def prettify_paper_name(p):
    p = re.sub("\(.*?\)", "", p)

    colon = p.find(':')
    if colon != -1:
        p = p[:colon]

    if p[len(p)-1] == ' ':
        p = p[:(len(p) -1)]
    return p


def get_records(date):
    records = []

    day = datetime.datetime.strftime(date, '%Y/%m/%d')
    search = "https://gallica.bnf.fr/SRU?version=1.2&operation=searchRetrieve"\
             "&exactSearch=false&collapsing=true&version=1.2"\
             "&query=(dc.type%20all%20%22fascicule%22)%20and"\
             "%20(ocr.quality%20all%20%22Texte%20disponible%22)%20and%20"\
             "(gallicapublication_date=%22" + day + "%22)"\
             "&suggest=10&keywords=#resultat-id-1"

    logger.info("Search URL: %s" % search)

    try:
        xml = urllib.request.urlopen(search).read()
        doc = etree.fromstring(xml)
        doc_records = doc[4]
        for i in range(len(doc_records)):
            for child in list(doc_records[i]):
                if 'recordData' in child.tag:
                    record_data = child

            paper_name = ''
            for child in list(record_data[0]):
                if 'title' in child.tag:
                    # take the shortest title (there are two versions)
                    if (paper_name == '') or ((paper_name != '') and len(child.text) < len(paper_name)):
                        paper_name = child.text
                        logger.info("new paper: %s" % paper_name)

            paper_name = prettify_paper_name(paper_name)

            for child in list(doc_records[i]):
                if 'extraRecordData' in child.tag:
                    extra_record_data = child
                    break

            uri = ''
            raw_text = ''
            thumbnail = ''
            for child in list(extra_record_data):
                if 'uri' in child.tag:
                    uri = child.text
                if 'thumbnail' in child.tag:
                    thumbnail = child.text
                    raw_text = thumbnail.replace('thumbnail', 'texteBrut')
                    url = thumbnail.replace('.thumbnail', '')

            r = {'uri': uri, 'raw_text': raw_text, 'url': url, 'paper': paper_name}
            records.append(r)
    except Exception as e:
        logger.error(e)
        
    return records


def blocks(record):
    """
    Returns blocks of ocr text from a page, limited to the first 120 characters
    along with some metadata associated with the block: height, width
    number of dictionary words, etc.
    """
    url = 'https://gallica.bnf.fr/RequestDigitalElement?O=' + record['uri'] + '&E=ALTO&Deb=1'
    ns = {'alto': 'http://bibnum.bnf.fr/ns/alto_prod'}
    dictionary = Dictionary()

    blocks = []
    try:
        # some pages are not digitized, and don't have ocr
        xml = urllib.request.urlopen(url).read()
        p = etree.XMLParser(encoding='utf-8')
        doc = etree.fromstring(xml, parser=p)
    except Exception as e:
        logger.error(e)
        return blocks

    for b in doc.xpath('//alto:TextBlock', namespaces=ns): 
        words = []
        text_length = 0
        confidence = 0.0
        string_count = 0
        dictionary_words = 0.0
        for l in b.xpath('alto:TextLine', namespaces=ns):
            for s in l.xpath('alto:String[@CONTENT]', namespaces=ns):
                string = s.attrib['CONTENT']
                words.append(string)
                text_length += len(string)
                confidence += float(s.attrib['WC'])
                string_count += 1
                if dictionary.is_word(string):
                    dictionary_words += 1

        if string_count == 0 or dictionary_words == 0:
            continue

        words = ' '.join(words)
        h = int(b.attrib['HEIGHT'])
        w = int(b.attrib['WIDTH'])
        vpos = float(b.attrib['VPOS'])

        if record['paper'] in config.paper_blacklist or record['paper'].lower().startswith("bulletin"):
            print("Paper %s is blacklisted, skipping." % record['paper'])
            continue

        # Skip lines that are heuristically unlikely to be headlines
        # TODO : move to a dedicated function
        if vpos < 600:
            continue
        if record['paper'] == 'Le Journal':
            if vpos < 1000:
                logger.info("Ignoring block because Le Journal and vpos < 1000")
                continue
        if record['paper'] == 'Le Rappel':
            if vpos < 1700:
                logger.info("Ignoring block because le rappel and vpos < 1000")
                continue

        # ignore text > 80 characters, we're looking for short headlines
        if len(words) > 80:
            continue

        word_ratio = dictionary_words / string_count
        confidence = confidence / string_count

        b = {'text': words, 'confidence': confidence,
             'height': h, 'width': w, 'word_ratio': word_ratio,
             'vpos': vpos, 'url': record['url'], 'paper': record['paper']} 

        logger.info("Appending new block: %s" % b)
        blocks.append(b)

    return blocks

def cmp_block(block):
    return ((block['height'] * block['width']) ^ 2) * block['word_ratio'] * len(block['text']) * (1 / block['vpos']) * block['confidence'] * block['word_ratio']

def get_frontpage(headline, date):
    fname = "./%s/%s.jpeg" % (config.assets, datetime.datetime.strftime(date, '%d/%m/%Y').replace('/', '_') )

    source_url = headline['url'] + "/f1.highres"
    with open(fname, "wb") as f:
        f.write(requests.get(source_url).content)
    
    if os.path.exists(fname):
        return fname
    else:
        return ""

def format_status(headline, date):
    d = datetime.datetime.strftime(date, '%d/%m/%Y')
    remaining = 280 - (len(d) + len(headline['url'])) 
    snippet = headline['text'][0:remaining]

    if headline['paper'] != '':
        msg = '%s: "%s" (%s) %s' % (d, snippet, headline['paper'], headline['url'])
    else:
        msg = '%s: "%s" %s' % (d, snippet, headline['url'])
    return msg

class Dictionary:
    def __init__(self):
        self._open()

    def is_word(self, w):
        w = w.lower()
        w = ''.join(e for e in w if e.isalnum())
        return w in self.db

    def _open(self):
        try:
            self.db = dbm.ndbm.open('dictionary', 'r')
        except dbm.error:
            self._make()
            self.db = dbm.ndbm.open('dictionary', 'r')

    def _make(self):
        word_file = config.dico
        if not os.path.isfile(word_file):
            raise Exception("can't find word file: %s" % word_file)
        db = dbm.ndbm.open('dictionary', 'c')
        for word in open(word_file, 'r'):
            word = word.lower().strip()
            db[word] = '1'
        db.close()


if __name__ == '__main__':
    main(sys.argv)
