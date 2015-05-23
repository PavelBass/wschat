# coding: utf-8
import os
import logging
import tornado.web
import tornado.websocket
import tornado.escape

from tornado.log import enable_pretty_logging
enable_pretty_logging()
from tornado.ioloop import IOLoop
from tornado import gen

try:
    import redis
except ImportError:
    redis = None
    logging.warn(' redis-py is not installed, all data will be lost on restart')

if redis is not None:
    try:
        r = redis.Redis()
        r.info()
        from .db import DBRedis as DBInterface
    except redis.exceptions.ConnectionError:
        logging.warn('Cant connect to REDIS, all data will be lost on restart')
        from .db import DBPython as DBInterface
else:
    from .db import DBPython as DBInterface

DB = DBInterface()


class MainHandler(tornado.web.RequestHandler):
    def initialize(self):
        self.db = DB

    @gen.coroutine
    def get(self):
        usr = self.current_user
        if usr is not None:
            usr = tornado.escape.xhtml_escape(usr)
        self.render("index.html", usr=usr, error='', rooms=self.all_rooms)

    @gen.coroutine
    def post(self):
        # Logout
        logout = self.get_argument('logout', '')
        if logout == 'logout':
            self.clear_cookie('user', '')
            self.redirect('/')
            return
        # Login/Registration
        error = ''
        create = self.get_argument('create', '')
        login, password = self.get_argument('login', None), self.get_argument('pass', None)
        if None in (login, password) or not (login and password):
            error = 'Empty field'
            self.render('index.html', usr=None, error=error, rooms=self.all_rooms)
            return
        if create:
            user = self.db.new_user(login, password)
            if user is None:
                error = 'Such user already exists'
        else:
            user = self.db.is_correct_user(login, password)
            if user is None:
                error = "No such user"
            elif not user:
                error = 'Wrong password'
        if error:
            self.render('index.html', usr=None, error=error, rooms=self.all_rooms)
            return
        self.set_secure_cookie('user', login)
        self.redirect('/')

    def get_current_user(self):
        user = self.get_secure_cookie('user')
        if self.db.is_correct_user(user, '') is None:
            # Non-existent in database user
            self.clear_cookie('user')
            user = None
        return user

    @property
    def all_rooms(self):
        return self.db.all_rooms


class ChatHandler(tornado.websocket.WebSocketHandler):
    waiters = dict()
    for room in DB.all_rooms:
        waiters[room] = set()

    def __init__(self, *args, **kwargs):
        super(ChatHandler, self).__init__(*args, **kwargs)
        self.db = DB

    def open(self):
        user = self.current_user
        if user is None:
            self.connect_to_room(self.db.default_room)
        else:
            for room in self.db.get_current_rooms(user):
                self.connect_to_room(room)

    def on_close(self):
        for room in self.current_rooms:
            if self in self.waiters[room]:
                self.waiters[room].remove(self)

    def on_message(self, mess):
        rooms = self.current_rooms
        user = self.current_user
        if user is None:
            user = 'Anonymous'
        mess = '%s: %s' % (user, tornado.escape.xhtml_escape(mess))
        for room in rooms:
            self.db.new_message(room, mess)
            self.send_to_waiters(room, mess)

    def send_to_waiters(self, room, mess):
        mess = 'MESSAGE:[%s] %s' % (room, mess)
        for waiter in self.waiters[room]:
            try:
                waiter.write_message(mess)
            except:
                pass

    def connect_to_room(self, room):
        # NOTE: you must check if room exists before calling this method
        self.waiters[room].add(self)
        self.send_server_message('You are connected to room: "%s"' % room)
        user = self.current_user
        if user is not None and room not in self.current_rooms:
            self.db.add_room_to_current(user, room)
        history = self.db.get_room_history(room)
        self.send_history(room, history)

    def disconnect_from_room(self, room):
        # NOTE: you must check if room exists before calling this method
        self.waiters[room].remove(self)
        self.send_server_message('You are disconnected from room: "%s"' % room)

    def send_server_message(self, mess):
        mess = 'SERVER:%s' % mess
        mess = tornado.escape.xhtml_escape(mess)
        self.write_message(mess)

    def send_history(self, room, history):
        for mess in history:
            mess = 'MESSAGE:[%s] %s' % (room, mess)
            self.write_message(mess)

    def get_current_user(self):
        return self.get_secure_cookie('user')

    @property
    def current_rooms(self):
        user = self.current_user
        return self.db.get_current_rooms(user)


def main(host, port):
    handlers = [
        (r"/", MainHandler),
        (r"/chat", ChatHandler)
    ]
    sett = {
        'cookie_secret': '%RamblerTask-WebSocketChat%',
        'template_path': os.path.join(os.path.dirname(__file__), 'templates'),
        'static_path': os.path.join(os.path.dirname(__file__), 'static'),
        'xsrf_cookies': True,
    }
    app = tornado.web.Application(handlers, **sett)
    app.listen(port, host)
    IOLoop.current().start()


def run(host='localhost', port=8080):
    main(host, port)

if __name__ == '__main__':
    run()