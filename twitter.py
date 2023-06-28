"""
Little utilities around tweepy for twitter interaction.
"""

import os, sys
import tweepy
import config

import logging

# v1, still necessary for image upload, see https://github.com/tweepy/tweepy/discussions/1954
auth = tweepy.OAuthHandler(config.twitter_oauth_consumer_key, 
                           config.twitter_oauth_consumer_secret)
auth.set_access_token(config.twitter_oauth_access_token_key,
                      config.twitter_oauth_access_token_secret)
api_v1 = tweepy.API(auth)

# v2
twitter = tweepy.Client(
        consumer_key=config.twitter_oauth_consumer_key,
        consumer_secret=config.twitter_oauth_consumer_secret,
        access_token=config.twitter_oauth_access_token_key,
        access_token_secret=config.twitter_oauth_access_token_secret)

def tweet(msg, logger, dry_run = False, img = ""):
    try:
        logger.info("Tweeting: %s" % msg)
        if not dry_run:
            if img and os.stat(img).st_size < 3072 * 1024: # 3 MB
                logger.info("Tweeting with media") 
                media = api_v1.media_upload(img)
                twitter.create_tweet(text=msg, media_ids=[media.media_id])
            else:
                logger.warning("Could not tweet with media, size: %d" % os.stat(img).st_size)
                twitter.create_tweet(text=msg)
    except Exception as e:
        logger.error("There was an exception tweeting: %s", e)

