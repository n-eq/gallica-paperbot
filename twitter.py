"""
Little utilities around tweepy for twitter interaction.
"""

import sys
import tweepy
import config
import os

auth = tweepy.OAuthHandler(config.twitter_oauth_consumer_key, 
                           config.twitter_oauth_consumer_secret)
auth.set_access_token(config.twitter_oauth_access_token_key,
                      config.twitter_oauth_access_token_secret)
twitter = tweepy.API(auth)

def tweet(msg, dry_run = False, img = ""):
    try:
        print("Tweeting: ", msg)
        if not dry_run:
            if img and os.stat(img).st_size < 3072 * 1024: # 3 MB
                print("Tweeting with media") 
                twitter.update_with_media(img, msg)
            else:
                print("Could not tweet with media, size: %d" % os.stat(img).st_size)
                twitter.update_status(msg)
    except Exception as e:
        print("There was an exception tweeting.")
        print(e)

if __name__ == '__main__':
    tweet(sys.argv[1])


