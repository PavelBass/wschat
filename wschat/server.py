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
        """ Called on POST HTTP request from user.
            Allowed requests to Login, Register, Logout
        :return:
        """
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
        # Check empty/not given fields
        if None in (login, password) or not (login and password):
            error = 'Empty field'
            self.render('index.html', usr=None, error=error, rooms=self.all_rooms)
            return
        if create:
            # Registration
            user = self.db.new_user(login, password)
            if user is None:
                error = 'Such user already exists'
        else:
            # Login
            user = self.db.is_correct_user(login, password)
            if user is None:
                error = "No such user"
            elif not user:
                error = 'Wrong password'
        if error:
            # Error during Login/Registration
            self.render('index.html', usr=None, error=error, rooms=self.all_rooms)
            return
        self.set_secure_cookie('user', login)
        self.redirect('/')

    def get_current_user(self):
        """ Get authorized user from cookie record """
        user = self.get_secure_cookie('user')
        if self.db.is_correct_user(user, '') is None:
            # Non-existent in database user
            self.clear_cookie('user')
            user = None
        return user

    @property
    def all_rooms(self):
        """ Value of all created rooms, stored in DataBase """
        return self.db.all_rooms


class ChatHandler(tornado.websocket.WebSocketHandler):
    waiters = dict()
    for room in DB.all_rooms:
        waiters[room] = set()

    def __init__(self, *args, **kwargs):
        super(ChatHandler, self).__init__(*args, **kwargs)
        self.db = DB
        self._user = None
        self.known_commands = dict(
            login=self.command_login,
            logout=self.command_logout,
            register=self.command_register
        )

    def open(self):
        user = self.get_secure_cookie('user')
        if user is None:
            self.connect_to_room(self.db.default_room)
        else:
            self._user = user
            for room in self.db.get_current_rooms(user):
                self.connect_to_room(room)

    def on_close(self):
        # Remove self from message waiters (unsubscribe)
        for room in self.current_rooms:
            if self in self.waiters[room]:
                self.waiters[room].remove(self)

    def on_message(self, mess):
        """ Called when was recieved a message. Checking and
            saving message. If message contains contains
            command to server, call suitable method.
        :param mess: utf-8 string, if mess starts with '#' -
            it is a command for server. In general view:
            '#command arg1 arg2 arg3 ... argN'
        """
        rooms = self.current_rooms
        user = self.current_user
        if user is None:
            user = 'Anonymous'

        if mess.startswith('#'):
            # Command
            mess = mess[1:].split(' ', 1)
            command = mess[0]
            args = mess[1] if len(mess) - 1 else ''
            if command not in self.known_commands:
                self.send_server_message('Unknown command')
            else:
                self.known_commands[command.lower()](args)
        else:
            # Message
            mess = '%s: %s' % (user, tornado.escape.xhtml_escape(mess))
            for room in rooms:
                self.db.new_message(room, mess)
                self.send_to_waiters(room, mess)

    def send_to_waiters(self, room, mess):
        """ Send received message to all waiters of room.
            This method sends users messages only, not
            server answers. General view of sending
            message: "MESSAGE:[room] nickname: mess"
        :param room: room name where message was sent
        :param mess: received message
        """
        mess = 'MESSAGE:[%s] %s' % (room, mess)
        for waiter in self.waiters[room]:
            try:
                waiter.write_message(mess)
            except:
                pass

    def connect_to_room(self, room):
        """ Add self to waiters of rooms (subscribe)
            NOTE: you must check if room exists
              before calling this method
        :param room: room name to subscribe
        """
        self.waiters[room].add(self)
        self.send_server_message('You are connected to room: "%s"' % room)
        user = self.current_user
        if user is not None and room not in self.current_rooms:
            self.db.add_room_to_current(user, room)
        history = self.db.get_room_history(room)
        self.send_history(room, history)

    def disconnect_from_room(self, room):
        """ Remove self from waiters of room (unsubscribe)
            NOTE: you must check if room exists
              before calling this method
        :param room: room name to unsubscribe
        """
        self.waiters[room].remove(self)
        self.send_server_message('You are disconnected from room: "%s"' % room)

    def send_server_message(self, mess):
        """ Send server message to user.
            This method sends server answers only, not
            users messages. General view of sending
            message: "SERVER:mess"
        :param mess: server message
        """
        mess = 'SERVER:%s' % mess
        mess = tornado.escape.xhtml_escape(mess)
        self.write_message(mess)

    def send_history(self, room, history):
        """ Send last N messages of room to user.
        :param room: room name
        :param history: list/tuple of last messages taken from db.
            DataBase stores messages as "user: mess", so for
            general view "MESSAGE:[room] user: mess" we need to
            add "MESSAGE:[room] "
        """
        for mess in history:
            mess = 'MESSAGE:[%s] %s' % (room, mess)
            self.write_message(mess)

    @property
    def current_user(self):
        """ Rewritten property of current user. By default tornado
            caches value given from "get_current_user", so we need
            rewrite it to receive actual user.
        """
        return self.get_current_user()

    def get_current_user(self):
        """ Rewritten method to get current user. Our Handler
            stores own value of current user per connection.
        """
        return self._user

    @property
    def current_rooms(self):
        """ List/tuple of rooms to which the user has been connected
        """
        user = self.current_user
        return self.db.get_current_rooms(user)

    def command_login(self, login_password):
        login_password = filter(lambda x: x, login_password.strip(' ').split(' '))
        mess = ''
        try:
            login, password = login_password[0], login_password[1]
            user = self.db.is_correct_user(login, password)
        except IndexError:
            mess = 'Wrong command usage'
        if mess:
            pass
        elif user is None:
            mess = 'No such user'
        elif not user:
            mess = 'Password incorrect'
        else:
            mess = 'You are logged in as "%s"' % login
            self._user = login
        self.send_server_message(mess)

    def command_logout(self, args):
        self._user = None
        self.send_server_message('You are logged out')

    def command_register(self, login_password):
        login_password = filter(lambda x: x, login_password.strip(' ').split(' '))
        mess = ''
        try:
            login, password = login_password[0], login_password[1]
        except IndexError:
            mess = 'Wrong command usage'
        if not mess:
            user = self.db.new_user(login, password)
            if user is None:
                mess = 'Such user already exists'
            else:
                mess = 'User "%s" successfully created. Try to login.' % login
        self.send_server_message(mess)


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