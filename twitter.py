"""
Little utilities around tweepy for twitter interaction.
"""

import os, sys
import tweepy
import config

import logging

auth = tweepy.OAuthHandler(config.twitter_oauth_consumer_key, 
                           config.twitter_oauth_consumer_secret)
auth.set_access_token(config.twitter_oauth_access_token_key,
                      config.twitter_oauth_access_token_secret)
twitter = tweepy.API(auth)

def tweet(msg, logger, dry_run = False, img = ""):
    try:
        logger.info("Tweeting: %s" % msg)
        if not dry_run:
            if img and os.stat(img).st_size < 3072 * 1024: # 3 MB
                logger.info("Tweeting with media") 
                twitter.update_with_media(img, msg)
            else:
                logger.warning("Could not tweet with media, size: %d" % os.stat(img).st_size)
                twitter.update_status(msg)
    except Exception as e:
        logger.error("There was an exception tweeting: %s", e)

