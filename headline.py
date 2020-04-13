#!/usr/bin/env python

import os
import dbm
import sys
import urllib, urllib2
import datetime
import re

from lxml import etree

import twitter
import config

def main(argv):
    dry_run = False
    if len(argv) > 1: # for testing
        date = datetime.datetime.strptime(argv[1], '%Y/%m/%d')
        if (len(argv) > 2 and argv[2] == "--dryrun"):
            dry_run = True
    else:
        today = datetime.date.today()
        date = datetime.date(today.year-100, today.month, today.day)

    sys.stdout = open(config.logfile, 'a')

    print("Running script for " + date.strftime("%m/%d/%Y"))

    records = get_records(date)

    headlines = []
    for r in records:
        headlines.extend(blocks(r))

    headlines.sort(tweetability)
    print("Sorted headlines: ")
    for h in headlines[:10]:
        print(h['text'].encode('utf-8'), h['paper_name'])

    if (len(headlines) > 0):
        msg = twitter_msg(headlines[0], date)
        twitter.tweet(msg, dry_run)
    else:
        print("No headlines found.")

    sys.stdout.close()


def prettify_paper_name(p):
    p = re.sub("\(.*?\)", "", p)
    print("p after deleting parentheses: ", p)

    colon = p.find(':')
    if colon != -1:
        p = p[:colon]

    print("Stripping paper name: ", p)
    if p[len(p)-1] == ' ':
        p = p[:(len(p) -1)]
        print("Removing ending whitespace: ", p)
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

    print("Search URL: ", search)

    try:
        xml = urllib2.urlopen(search).read()
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
                        print("new  paper: ", paper_name)

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
        print(e)
        
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
        xml = urllib.urlopen(url).read()
        doc = etree.fromstring(xml)
    except Exception as e:
        print(e)
        return blocks

    for b in doc.xpath('//alto:TextBlock', namespaces=ns): 
        text = []
        text_length = 0
        confidence = 0.0
        string_count = 0
        dictionary_words = 0.0
        for l in b.xpath('alto:TextLine', namespaces=ns):
            for s in l.xpath('alto:String[@CONTENT]', namespaces=ns):
                string = s.attrib['CONTENT']
                text.append(string)
                text_length += len(string)
                confidence += float(s.attrib['WC'])
                string_count += 1
                if dictionary.is_word(string):
                    dictionary_words += 1

        if string_count == 0 or dictionary_words == 0:
            continue

        text = ' '.join(text)
        h = int(b.attrib['HEIGHT'])
        w = int(b.attrib['WIDTH'])
        vpos = float(b.attrib['VPOS'])

        # ignore masthead
        if vpos < 1800:
            continue

        # ignore text > 80 characters, we're looking for short headlines
        if len(text) > 80:
            continue

        word_ratio = dictionary_words / len(text)
        confidence = confidence / string_count

        b = {'text': text, 'confidence': confidence,
             'height': h, 'width': w, 'word_ratio': word_ratio,
             'vpos': vpos, 'url': record['url'], 'paper': record['paper']} 
        print("Appending new block:")
        print(b)

        blocks.append(b)

    return blocks

def tweetability(a, b):
    def index(block):
        return ((block['height'] * block['width']) ^ 2) * block['word_ratio'] * len(block['text']) * (1/block['vpos'])
    return cmp(index(b), index(a))


def twitter_msg(headline, date):
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
        if len(w) < 4:
            return False
        return self.db.has_key(w.encode('utf-8')) == 1

    def _open(self):
        try:
            self.db = dbm.open('dictionary', 'r')
        except dbm.error:
            self._make()
            self.db = dbm.open('dictionary', 'r')

    def _make(self):
        word_file = '/etc/dictionaries-common/words'
        if not os.path.isfile(word_file):
            raise Exception("can't find word file: %s" % word_file)
        db = dbm.open('dictionary', 'c')
        for word in open(word_file, 'r'):
            word = word.lower().strip()
            db[word] = '1'
        db.close()


if __name__ == '__main__':
    main(sys.argv)
