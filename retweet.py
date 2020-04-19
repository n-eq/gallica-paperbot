#!/usr/bin/env python

"""
Retweet people that look like they are finding interesting stuff on 
Gallica BNF. Sort the tweets based on an index that tries to get
a tweet's impressions (retweets, favs and user followers) and limit
the daily retweets to 5.

We remember which tweets we've already retweeted by setting the mtime
on touchfile to the date of the last tweet we've seen. We also take 
care not to retweet ourselves, and not to retweet other retweets, which
could create a literal echo chamber :-)

If a tweet also has links to other places than Gallica it won't get retweeted.
This is a conservative measure to prevent the spread of spam
and other weirdness.
"""

import os
import time
import config
import random
import datetime
import requests

import json

from twitter import twitter

def all_urls(tweet):
    for u in tweet.entities['urls']:
        url = u['expanded_url']
        try:
            r = requests.get(url)
            if not r.url.startswith('https://gallica.bnf.fr/ark:'):
                return False
        except:
            # if we couldn't fetch the URL we don't want to tweet it anyway
            return False
    return True

def retweetability(a, b):
    ret = cmp(a.retweet_count, b.retweet_count)
    if ret == 0:
        ret = cmp(a.favorite_count, b.favorite_count)
        if ret == 0:
            ret = cmp(a.user.followers_count, b.user.followers_count)
    return ret

touchfile = "last_retweet"

if os.path.isfile(touchfile):
    last = datetime.datetime.fromtimestamp(os.stat(touchfile).st_mtime)
else: 
    last = None

tweets = twitter.search("gallica", count=100)

tweets.sort(retweetability)

new_last = None

i = 0
for tweet in tweets:
    new_last = tweet.created_at
    if hasattr(tweet, 'retweeted_status'):
        continue
    if hasattr(tweet, 'possibly_sensitive') and tweet.possibly_sensitive:
        continue
    # Note : to avoid retweeting yourself add the user's @ to the block list
    if tweet.user.screen_name in config.block:
        continue
    if last and tweet.created_at <= last:
        continue
    if tweet.text.startswith("RT"):
        continue
    if not all_urls(tweet):
        continue
    
    try:
#         print("Tweet:")
#         print(json.dumps(tweet._json, indent=4, sort_keys=True))
#         print(tweet.text, tweet.retweet_count * 3, tweet.favorite_count * 2,  tweet.user.followers_count)
        tweet.retweet()
    except Exception as e:
        print e

    i += 1
    if i == config.max_daily_retweets:
        break
    time.sleep(random.randint(2, 30))

if not os.path.isfile(touchfile):
    open(touchfile, "w")

if new_last:
    os.utime(touchfile, (0, int(time.mktime(new_last.timetuple()))))
