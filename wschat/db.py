import hashlib
import collections
from abc import ABCMeta, abstractmethod, abstractproperty

try:
    import redis
except ImportError:
    redis = None


UserRecord = collections.namedtuple('UserRecord', "pass_hash allowed_rooms current_rooms")


class DB(object):
    __metaclass__ = ABCMeta

    _default_rooms = ('Free Chat', 'Python Developers', 'JavaScript Developers')
    _default_room = _default_rooms[0]

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
    def get_current_rooms(self, login):
        """ Return current rooms of user
        :param login: user login
        :return: list/tuple of current rooms
        """
        pass

    @abstractmethod
    def add_room_to_current(self, login, room):
        """ Add room to current rooms for user
            and rewrite his record in DataBase
        :param login: user login
        :param room: new room
        :return:
            None: if room doesn't exists
            True: if room was added
            False: if room was added before
        """
        pass

    @abstractmethod
    def remove_room_from_current(self, login, room):
        """ Remove room from current rooms for user
             and rewrite his record in DataBase
        :param login: user login
        :param room: room name to remove
        :return:
            False: if room was not added
            True: if room was successfully removed
        """
        pass

    @abstractmethod
    def get_room_history(self, room):
        """ Return room history (if room exists)

        :param room: room name
        :return:
            None: if room doesn't exists
            list: last 10 messages in room
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

    @property
    def default_room(self):
        return self._default_room

    @property
    def default_rooms(self):
        return self._default_rooms


class DBPython(DB):
    def __init__(self):
        self._users = dict()
        self._rooms = dict()
        for room in self.default_rooms:
            self._rooms[room] = list()

    def is_correct_user(self, login, password):
        user = self._users.get(login, None)
        if user is None:
            return
        return hashlib.md5(password).hexdigest() == user.pass_hash

    def get_current_rooms(self, login):
        rooms = (self.default_room,) if login not in self._users else self._users[login].current_rooms
        return rooms

    def add_room_to_current(self, login, room):
        user = self._users[login]
        rooms = list(user.current_rooms).append(room)
        self._users[login] = UserRecord(user.pass_hash, user.allowed_rooms, tuple(rooms))

    def remove_room_from_current(self, login, room):
        user = self._users[login]
        rooms = list(user.current_rooms)
        rooms.pop(room)
        self._users[login] = UserRecord(user.pass_hash, user.allowed_rooms, tuple(rooms))

    def get_room_history(self, room):
        history = self._rooms.get(room, None)
        if history is not None:
            history = history[-10:]
        return history

    def new_user(self, login, password):
        if login in self._users:
            return
        allowed_rooms = (self.default_room,)
        self._users[login] = UserRecord(hashlib.md5(password).hexdigest(), allowed_rooms, allowed_rooms)
        return allowed_rooms

    def new_room(self, room):
        if room in self._rooms:
            return False
        self._rooms[room] = list()
        return True

    def new_message(self, room, mess):
        self._rooms[room].append(mess)

    @property
    def all_rooms(self):
        return self._rooms.keys()


class DBRedis(DB):
    def __init__(self):
        self.r = redis.Redis()
