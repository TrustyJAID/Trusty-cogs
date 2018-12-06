import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify, box
import binascii
import random
import hashlib
from string import ascii_lowercase as lc, ascii_uppercase as uc



class Encoding(getattr(commands, "Cog", object)):
    """
        Convert messages into fun encodings
    """

    def __init__(self, bot):
        self.bot = bot
        self.table = {
    "A": ["00", "01", "10", "11", "00", "00", "00", "01", "01", "01", "10", "10", "10", "11", "11", "11"],
    "G": ["01", "10", "11", "00", "11", "10", "01", "11", "00", "10", "11", "00", "01", "00", "01", "10"],
    "C": ["10", "11", "00", "01", "10", "11", "10", "10", "11", "00", "01", "11", "00", "01", "00", "01"],
    "T": ["11", "00", "01", "10", "01", "01", "11", "00", "10", "11", "00", "01", "11", "10", "10", "00"]
    }
        # A = 00
        # G = 10
        # C = 11
        # T = 01
    def remove_non_ascii(self, data):
        msg = b""
        for char in data:
            if char in range(0, 127):
                msg += bytes(chr(char).encode("utf8"))
        return msg

    def search_words(self, data):
        count = 0
        try:
            for char in data:
                if ord(char) in range(47, 122):
                    count += 1
        except TypeError:
            for char in data:
                if char in range(47, 122):
                    count += 1
        try:
            if(count/len(data)) >= 0.75:
                return True
        except ZeroDivisionError:
            return False
        return False

    @commands.group(name='hash', invoke_without_command=True)
    async def hash_cmd(self, ctx, *, txt:str):
        """
            MD5 Encrypt Text
        """
        md5 = hashlib.md5(txt.encode()).hexdigest()
        await ctx.send('**MD5**\n'+md5)

    @hash_cmd.command(name='sha1')
    async def hash_sha1(self, ctx, *, txt:str):
        """
            SHA1 Encrypt Text
        """
        sha = hashlib.sha1(txt.encode()).hexdigest()
        await ctx.send('**SHA1**\n'+sha)

    @hash_cmd.command(name='sha256')
    async def hash_sha256(self, ctx, *, txt:str):
        """
            SHA256 Encrypt Text
        """
        sha256 = hashlib.sha256(txt.encode()).hexdigest()
        await ctx.send('**SHA256**\n'+sha256)

    @hash_cmd.command(name='sha512')
    async def hash_sha512(self, ctx, *, txt:str):
        """
            SHA512 Encrypt Text
        """
        sha512 = hashlib.sha512(txt.encode()).hexdigest()
        await ctx.send('**SHA512**\n'+sha512)


    @commands.group(name="encode")
    async def _encode(self, ctx: commands.Context):
        """Encode a string."""
        pass

    @commands.group(name="decode")
    async def _decode(self, ctx: commands.Context):
        """Decode a string."""
        pass

    @_encode.command(name="binary")
    async def encode_binary(self, ctx: commands.Context, *, message: str):
        """
            Encode text into binary sequences of 8
        """
        ascii_bin = ' '.join(bin(x)[2:].zfill(8) for x in message.encode('UTF-8'))
        await ctx.send(ascii_bin)

    @_decode.command(name="binary")
    async def decode_binary(self, ctx: commands.Context, *, message: str):
        """
            Decide binary sequences of 8
        """
        msg = message.replace(" ", "")
        bin_ascii = "".join([chr(int(msg[i:i+8],2)) for i in range(0,len(msg),8)])
        await ctx.send(bin_ascii)

    def rot_encode(self, n):
        """
            https://stackoverflow.com/questions/47580337/short-rot-n-decode-function-in-python
        """
        lookup = str.maketrans(lc + uc, lc[n:] + lc[:n] + uc[n:] + uc[:n])
        return lambda s: s.translate(lookup)

    @_encode.command(name="rot", aliases=["caeser"])
    async def caeser_encode(self, ctx: commands.Context, rot_key:int, *, message:str):
        """
            Encode a caeser cipher message with specified key
        """
        await ctx.send(self.rot_encode(rot_key)(message))

    @_decode.command(name="rot", aliases=["caeser"])
    async def caeser_decode(self, ctx: commands.Context, rot_key:int, *, message:str):
        """
            Decode a caeser cipher message with specified key
        """
        await ctx.send(self.rot_encode(-rot_key)(message))


    @_encode.command(name="dna")
    async def dna_encode(self, ctx: commands.Context, *, message: str):
        """
            Encodes a string into DNA 4 byte ACGT format
        """
        dna = {"00": "A", "01": "T", "10": "G", "11": "C"}
        message = message.strip(" ")
        binary = ' '.join(bin(x)[2:].zfill(8) for x in message.encode('UTF-8')).replace(" ", "")
        binlist = [binary[i:i+2] for i in range(0, len(binary), 2)]
        newmsg = ""
        count = 0
        for letter in binlist:
            newmsg += dna[letter]
            count += 1
            if count == 4:
                count = 0
                newmsg += " "
        await ctx.send(newmsg)


    @_decode.command(name="dna")
    async def dna_decode(self ,ctx: commands.Context, *, message: str):
        """
            Decodes a string of DNA in 4 byte ACGT format.
        """
        message = message.strip(" ")
        mapping = {}
        replacement = ""
        for i in range(0, 16):
            skip = [" ", "\n", "\r"]
            for character in message:
                if character in skip:
                    continue
                replacement += self.table[character][i]
            try:
                n = int("0b" + replacement, 2)
                mapping[i] = n.to_bytes((n.bit_length() + 7) // 8, 'big').decode("utf8", "ignore")
            except TypeError:
                pass
            replacement = ""
        num = 1
        new_msg = "Possible solutions:\n"
        for result in mapping.values():
            new_msg += str(num) + ": " + result + "\n"
            num += 1
        for page in pagify(new_msg, shorten_by=20):
            await ctx.send(f"```\n{page}\n```")
