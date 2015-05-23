import hashlib
import collections
from abc import ABCMeta, abstractmethod, abstractproperty

try:
    import redis
except ImportError:
    redis = None


UserRecord = collections.namedtuple('UserRecord', "pass_hash allowed_rooms current_room")
UserTemplate = collections.namedtuple('UserTemplate', "login, allowed_rooms")


class DB(object):
    __metaclass__ = ABCMeta

    default_rooms = ('Free Chat', 'Python Developers', 'JavaScript Developers')
    default_room = default_rooms[0]

    @abstractmethod
    def is_correct_user(self, login, password):
        """ Check if passed login is in base and password is correct

        :param login: passed login
        :param password: passed password (not hash)
        :return:
            None: if login not in database
            True: if login in database and password is correct
            False: if login in database but password is not correct
        """
        pass

    @abstractmethod
    def get_user_rooms(self, login):
        """ Return all rooms allowed for that user
            This method dont check if login is correct,
            you must check it before.
        :param login:
        :return: list of allowed rooms
        """
        pass

    @abstractmethod
    def get_user_current_room(self, login):
        """ Return current room of user
        :param login: user login
        :return: current room
        """
        pass

    @abstractmethod
    def set_user_current_room(self, login, room):
        """ Change current room for user if possible
            and rewrite his record in DataBase
        :param login: user login
        :param room: new room
        :return:
        """
        pass

    @abstractmethod
    def get_room_history(self, room):
        """ Return room history (if room exists)

        :param room: room name
        :return:
            None: if room doesn't exists
            list: last 50 messages in room
        """
        pass

    @abstractmethod
    def new_user(self, login, password):
        """ Create new user
        :param login: passed login
        :param password: passed password
        :return:
            None: if user already exists
            list: default allowed rooms
        """
        pass

    @abstractmethod
    def new_room(self, room):
        """ Create new room
        :param room: room name
        :return:
            False: if such room already exists
            True: after creation
        """
        pass

    @abstractmethod
    def new_message(self, room, mess):
        """ Save new message into room history
        :param room: room name
        :param mess: message
        :return: None
        """
        pass

    @abstractproperty
    def all_rooms(self):
        """ Return all existent rooms
        :return: list/tuple of rooms
        """
        pass


class DBPython(DB):
    def __init__(self):
        self.users = dict()
        self.rooms = dict()
        for room in self.default_rooms:
            self.rooms[room] = list()

    def is_correct_user(self, login, password):
        user = self.users.get(login, None)
        if user is None:
            return
        return hashlib.md5(password).hexdigest() == user.pass_hash

    def get_user_rooms(self, login):
        return self.users[login].allowed_rooms

    def get_user_current_room(self, login):
        room = self.default_room if login not in self.users else self.users[login].current_room
        return room

    def set_user_current_room(self, login, room):
        user = self.users[login]
        self.users[login] = UserRecord(user.pass_hash, user.allowed_rooms, room)

    def get_room_history(self, room):
        history = self.rooms.get(room, None)
        if history is not None:
            history = history[-10:]
            return history

    def new_user(self, login, password):
        if login in self.users:
            return
        allowed_rooms = [self.default_room]
        self.users[login] = UserRecord(hashlib.md5(password).hexdigest(), allowed_rooms, self.default_room)
        return allowed_rooms

    def new_room(self, room):
        if room in self.rooms:
            return False
        self.rooms[room] = list()
        return True

    def new_message(self, room, mess):
        self.rooms[room].append(mess)

    @property
    def all_rooms(self):
        return self.rooms.keys()


class DBRedis(DB):
    def __init__(self):
        self.r = redis.Redis()
