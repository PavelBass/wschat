# coding: utf-8
import os
import logging
import tornado.web
from tornado.ioloop import IOLoop


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class ChatHandler(tornado.web.RequestHandler):
    def get(self):
        pass

def main(port=8080, interface='localhost'):
    handlers = [
        (r"/", MainHandler),
        (r"/chat", ChatHandler)
    ]
    sett =  {
        'cookie_secret': '%RamblerTask-WebSocketChat%',
        'template_path': os.path.join(os.path.dirname(__file__), 'templates'),
        'static_path': os.path.join(os.path.dirname(__file__), 'static'),
        'xsrf_cookies': True,
    }
    app = tornado.web.Application(handlers, **sett)
    app.listen(port, interface)
    IOLoop.current().start()

def run():
    main()

if __name__ == '__main__':
    run()