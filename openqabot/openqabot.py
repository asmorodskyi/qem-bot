from logging import getLogger

import requests

from .loader.config import load_metadata
from .loader.qem import get_incidents


logger = getLogger("bot.openqabot")


class OpenQABot:
    def __init__(self, args):
        logger.debug("Bot initialization with %s" % args)
        self.dry = args.dry
        self.token = {"Authorization": "Token " + args.token}
        self.incidents = get_incidents(self.token)
        logger.info("%s incidents loaded from qem dashboard" % len(self.incidents))
        self.workers = load_metadata(
            args.configs, args.disable_aggregates, args.disable_incidents
        )
        self.post = []

    def post_qem(self, data, api):
        url = "http://dashboard.qam.suse.de" + api
        try:
            res = requests.put(url, headers=self.token, json=data)
        # TODO: exceptions handling
        except Exception as e:
            logger.exception(e)
            raise e

    def post_openqa(self, data):
        pass

    def __call__(self):
        logger.info("Starting bot mainloop")

        for worker in self.workers:
            self.post += worker(self.incidents, self.token)

        logger.info("Posting %s jobs" % len(self.post))
        if not self.dry:
            for job in self.post:
                logger.debug("Posting %s" % str(job))
                self.post_openqa(job["openqa"])
                self.post_qem(job["qem"], job["api"])

        return 0
