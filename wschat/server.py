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


class CommandsMixin(object):
    """ Mixin of commands
        Agreements:
          Naming: all mixin methods which implements commands
            starts with 'user_command_' prefix.
          Arguments: all commands methods must expect one argument -
            utf-8 string to recognize needed arguments itself, or
            ignore them
    """
    def __init__(self):
        # Original variable
        self.known_commands = dict(
            login=self.user_command_login,
            logout=self.user_command_logout,
            register=self.user_command_register,
            join=self.user_command_join_room,
            left=self.user_command_left_room,
            change=self.user_command_change_nick
        )
        # Must be overwritten
        self.db = None
        self._user = None

    # Child Implementation methods
    def send_server_message(self, mess):
        """ Must be overwritten """
        raise NotImplementedError('"send_server_message" method must be overwritten')

    def connect_to_room(self, room):
        """ Must be overwritten """
        raise NotImplementedError('"connect_to_room" method must be overwritten')

    def disconnect_from_room(self, room):
        """ Must be overwritten """
        raise NotImplementedError('"disconnect_from_room" method must be overwritten')

    @property
    def current_rooms(self):
        """ Must be overwritten """
        raise NotImplementedError('"current_rooms" property must be overwritten')

    @property
    def all_rooms(self):
        """ Must be overwritten """
        raise NotImplementedError('"all_rooms" property must be overwritten')

    @property
    def current_user(self):
        """ Must be overwritten """
        raise NotImplementedError('"current_user" property must be overwritten')

    # Original methods
    def recognize_command(self, mess):
        """ Recognize received command and try to call
            suitable method.
            NOTE: method detects only first word, so if command consist
                of few words, other part of command will be passed in
                arguments string.
        :param mess: utf-8 string received from user
        """
        mess = mess[1:].split(' ', 1)
        command = mess[0].lower()
        args = mess[1] if len(mess) - 1 else ''
        if command not in self.known_commands:
            self.send_server_message('Unknown command')
        else:
            self.known_commands[command.lower()](args)

    def user_command_login(self, login_password):
        """ Login user.
            Required command view: 'login user_login password'.
        :param login_password: separated part "user_login password"
        """
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
            # No error during login
            mess = 'You are logged in as "%s"' % login
            self._user = login
            if (self in self.waiters[self.db.default_room]
                and self.db.default_room not in self.current_rooms):
                self.db.add_room_to_current(login, self.db.default_room)

        self.send_server_message(mess)

    def user_command_logout(self, args):
        """ Logout.
            Just change own user value to None
        :param args: not needed. Ignored.
        """
        self._user = None
        self.send_server_message('You are logged out')

    def user_command_register(self, login_password):
        """ Register new user.
            Required command view: 'register user_login password'.
        :param login_password: separated part "user_login password"
        """
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

    def user_command_join_room(self, room_room):
        """ Adding self to waiters of room.
            Required command view: 'join room room_name'.
        :param room_room: separated part "room room_name"
        """
        room_room = room_room.strip(' ').split(' ', 1)
        mess = ''
        try:
            room, room_name = room_room[0], room_room[1]
        except IndexError:
            mess = 'Wrong command usage'
        if mess:
            pass
        elif room.lower() != 'room':
            mess = 'Unknown join'
        elif room_name.lower() not in map(lambda x: x.lower(), self.all_rooms):
            mess = 'Cannot join. Unknown room'
        else:
            # Find right room name writing
            for room in self.all_rooms:
                if room_name.lower() == room.lower():
                    room_name = room
                    break
            self.connect_to_room(room_name)
        if mess:
            self.send_server_message(mess)

    def user_command_left_room(self, room_room):
        """ Removing self from waiters of room.
            Required command view: 'left room room_name'.
        :param room_room: separated part "room room_name"
        """
        room_room = room_room.strip(' ').split(' ', 1)
        mess = ''
        try:
            room, room_name = room_room[0], room_room[1]
        except IndexError:
            mess = 'Wrong command usage'
        if mess:
            pass
        elif room.lower() != 'room':
            mess = 'What must I left?'
        elif room_name.lower() not in map(lambda x: x.lower(), self.current_rooms):
            mess = 'You were not joined to room "%s"' % room_name
        else:
            # Find right room name writing
            for room in self.current_rooms:
                if room_name.lower() == room.lower():
                    room_name = room
                    break
            self.disconnect_from_room(room_name)
        if mess:
            self.send_server_message(mess)

    def user_command_change_nick(self, args):
        """ Changing nickname in room or all rooms
            Required command view: 'change nick room_name new_nick'
        :param args: separated part 'nick room_name new_nick'
        """
        mess, room, nick = ['']*3
        command, s, args = args.partition(' ')
        # Parsing args
        if command.lower() != 'nick':
            mess = 'What must I change?'
        else:
            args = args.strip(' ')
            if args and args[0] in ['"', "'"]:
                room, s, args = args[1:].partition(args[0])
                room = room.strip(' ')
                nick = args.strip(' ')
                if nick and nick[0] in ['"', "'"]:
                    nick, s, trash = nick[1:].partition(nick[0])
            elif args:
                room, nick = args.split(' ', 1)
                nick = nick.strip(' ')
        # Checking arguments
        if mess:
            pass
        elif not(room and nick):
            mess = 'Wrong command usage'
        elif room != '*' and room.lower() not in map(lambda x: x.lower(), self.current_rooms):
            mess = 'You were not joined to room "%s"' % room
        else:
            # Find right room name writing
            rooms = self.current_rooms
            if room != '*':
                for _room in self.current_rooms:
                    if room.lower() == _room.lower():
                        rooms = [_room]
                        break
            for room in rooms:
                mess = 'Your nick changed to "%s" in room "%s"' % (nick, room)
                self.db.change_nick_in_room(self.current_user, room, nick)
                self.send_server_message(mess)


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
        self.db.add_room_to_current(login, self.db.default_room)
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


class ChatHandler(tornado.websocket.WebSocketHandler, CommandsMixin):
    waiters = dict()
    for room in DB.all_rooms:
        waiters[room] = set()

    def __init__(self, *args, **kwargs):
        super(ChatHandler, self).__init__(*args, **kwargs)
        self.db = DB
        self._user = None

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
        """ Called when was received a message. Checking and
            saving message. If message contains contains
            command to server, call suitable method.
        :param mess: utf-8 string, if mess starts with '#' -
            it is a command for server. In general view:
            '#command arg1 arg2 arg3 ... argN'
        """
        rooms = self.current_rooms
        user = self.current_user
        if mess.startswith('#'):
            # Command
            self.recognize_command(mess)
        else:
            if not list(self.current_rooms):
                self.send_server_message('You are not connected to any room')
            for room in rooms:
                nick = self.db.get_current_nick(user, room)
                # Message
                _mess = '%s: %s' % (nick, tornado.escape.xhtml_escape(mess))
                self.db.new_message(room, _mess)
                self.send_to_waiters(room, _mess)

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
        user = self.current_user
        current_rooms = set(self.current_rooms)
        for _room in self.current_rooms:
            if self not in self.waiters[_room]:
                current_rooms.remove(_room)
        if user is None:
            allowed_rooms = [self.db.default_room]
        else:
            allowed_rooms = set(self.all_rooms) - current_rooms
        if self in self.waiters[room]:
            mess = 'You are already connected to room "%s"' % room
        elif room not in allowed_rooms:
            mess = 'You cant connect to room "%s"' % room
        else:
            self.waiters[room].add(self)
            if room not in current_rooms:
                self.db.add_room_to_current(user, room)
            mess = 'You are connected to room: "%s" as "%s"' % \
                   (room, self.db.get_current_nick(user, room))
            history = self.db.get_room_history(room)
            self.send_history(room, history)
        self.send_server_message(mess)

    def disconnect_from_room(self, room):
        """ Remove self from waiters of room (unsubscribe)
            NOTE: you must check if room exists
              before calling this method
        :param room: room name to unsubscribe
        """

        self.waiters[room].remove(self)
        self.db.remove_room_from_current(self.current_user, room)
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
        if user is None:
            droom = self.db.default_room
            return [droom] if self in self.waiters[droom] else list()
        else:
            return self.db.get_current_rooms(user)

    @property
    def all_rooms(self):
        """ Value of all created rooms, stored in DataBase """
        return self.db.all_rooms


def main(host, port):
    handlers = [
        (r"/", MainHandler),
        (r"/chat", ChatHandler)
    ]#join room Python Developers
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