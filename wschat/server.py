# coding: utf-8
import os
import logging
import hashlib
import collections
import tornado.web
import tornado.websocket
import tornado.escape

from tornado.ioloop import IOLoop
from tornado import gen


UserRecord = collections.namedtuple('UserRecord', "pass_hash allowed_rooms")
UserTemplate = collections.namedtuple('UserTemplate', "login, allowed_rooms")


class DBImitation(object):
    def __init__(self):
        self.users = dict()
        self.rooms = {0: list()}

    def is_correct_user(self, login, password):
        ''' Check if passed login is in base and password is correct

        :param login: passed login
        :param password: passed password (not hash)
        :return:
            None: if login not in database
            True: if login in database and password is correct
            False: if login in database but password is not correct
        '''
        user = self.users.get(login, None)
        if user is None:
            return
        return hashlib.md5(password).hexdigest() == user.pass_hash

    def get_user_rooms(self, login):
        ''' Return all rooms allowed for that user
            This method dont check if login is correct,
            you must check it before.
        :param login:
        :return: list of allowed rooms
        '''
        return self.users[login].allowed_rooms

    def get_room(self, room):
        ''' Return room history (if room exists)

        :param room: room name
        :return:
            None: if room doesn't exists
            list: last 50 messages in room
        '''
        room = self.rooms.get(room, None)

    def new_user(self, login, password):
        ''' Create new user
        :param login: passed login
        :param password: passed password
        :return:
            None: if user already exists
            list: default allowed rooms
        '''
        if login in self.users:
            return
        allowed_rooms = [0]
        self.users[login] = UserRecord(hashlib.md5(password).hexdigest(), allowed_rooms)
        return allowed_rooms

    def new_room(self, room):
        ''' Create new room
        :param room: room name
        :return:
            False: if such room already exists
            True: after creation
        '''
        if room in self.rooms:
            return False
        self.rooms[room] = list()
        return True

DB = DBImitation()

class MainHandler(tornado.web.RequestHandler):
    def initialize(self):
        self.db = DB

    @gen.coroutine
    def get(self):
        usr = self.current_user
        if usr is not None:
            usr = tornado.escape.xhtml_escape(usr)
        self.render("index.html", usr=usr, error=None)

    @gen.coroutine
    def post(self):
        logout = self.get_argument('logout', '')
        if logout == 'logout':
            self.clear_cookie('user', '')
            self.redirect('/')
            return
        error = ''
        create = self.get_argument('create', '')
        login, password = self.get_argument('login', None), self.get_argument('pass', None)
        if None in (login, password) or not (login and password):
            error = 'Empty field'
            self.render('index.html', usr=None, error=error)
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
            else:
                user = self.db.get_user_rooms(login)
                user = UserTemplate(login, user)
        if error:
            self.render('index.html', usr=None, error=error)
            return
        self.set_secure_cookie('user', login)
        self.redirect('/')

    def get_current_user(self):
        user = self.get_secure_cookie('user')
        if user and user not in self.db.users:
            self.clear_cookie('user')
            user = None
        return None if not user else user

    # @property
    # def current_user(self):
    #     user = super(MainHandler, self).current_user
    #     #if user is None:
    #     #    user = self.get_current_user()
    #     #    print user
    #     return user

class ChatHandler(tornado.websocket.WebSocketHandler):
    @gen.coroutine
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