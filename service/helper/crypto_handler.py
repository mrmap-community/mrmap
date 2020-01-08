"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 07.01.20

"""
import hashlib

import os
from cryptography.fernet import Fernet

from service.settings import EXTERNAL_AUTHENTICATION_FILEPATH


class CryptoHandler:

    def __init__(self, msg: str = None, key: str = None):
        self.message = msg
        self.key = key
        self.crypt_message = None

        if key is None:
            self.key = self.generate_key()

    def encrypt(self):
        """ Encrypts the message using the key

        Args:
        Returns:
             nothing
        """
        # encode input msg to byte for encryption
        msg = self.message.encode("ascii")
        cipher_suite = Fernet(self.key)
        self.crypt_message = cipher_suite.encrypt(msg)

    def decrypt(self):
        """ Decrypts the crypt_message

        Args:
        Returns:
             nothing
        """
        self.crypt_message = self.crypt_message
        cipher_suite = Fernet(self.key)
        self.message = cipher_suite.decrypt(self.crypt_message)
        if isinstance(self.message, bytes):
            self.message.decode("ascii")

    def generate_key(self):
        """ Generates a random string of a certain length

        Args:
        Returns:
            str
        """
        return Fernet.generate_key()

    def write_key_to_file(self, filepath, key):
        """ Stores the key in a file on the local file system.

        Args:
            filepath (str): The absolute path, including the file's name
            key: The key
        Returns:
        """
        try:
            file = open(filepath, "wb")  # open file in write-bytes mode
            file.write(key)
            file.close()
        except FileNotFoundError:
            # directory might not exist yet
            tmp = filepath.split("/")
            del tmp[-1]
            dir_path = "/".join(tmp)
            os.mkdir(dir_path)

            # try again
            self.write_key_to_file(filepath, key)

    def get_key_from_file(self, metadata_id: int):
        """ Reads a stored key from a file

        Args:
            metadata_id (int): The metadata id, which identifies the correct key
        Returns:
        """
        filepath = "{}/md_{}.key".format(EXTERNAL_AUTHENTICATION_FILEPATH, str(metadata_id))

        file = open(filepath, "rb")
        key = file.read()
        return key

    def sha256(self, _input: str):
        """ Returns the SHA-256 hash of an input string

        Args:
            _input (str): The input
        Returns:
        """
        m = hashlib.sha256()
        m.update(_input.encode("UTF-8"))
        return m.hexdigest()
