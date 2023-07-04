from typing import Optional

__all__ = ["JavaRandom"]


class JavaRandom:
    """
    Java's Random() partially implemented in Python
    https://docs.oracle.com/javase/8/docs/api/java/util/Random.html
    """

    def __init__(self, seed: int):
        self.set_seed(seed)

    def next(self, bits: int) -> int:
        self.seed = (self.seed * 0x5DEECE66D + 0xB) & ((1 << 48) - 1)
        return self._rshift(self.seed, (48 - bits))

    def next_int(self, n: Optional[int]) -> int:
        if n is None:
            return self.next(32)
        if n <= 0:
            raise ValueError
        if (n & -n) == n:
            return n * self.next(31) >> 31
        bits = self.next(31)
        val = bits % n
        while bits - val + (n - 1) < 0:
            bits = self.next(31)
            val = bits % n
        return val

    def set_seed(self, seed: int):
        self.seed = (seed ^ 0x5DEECE66D) & ((1 << 48) - 1)
        return self.seed

    @staticmethod
    def _rshift(val: int, n: int) -> int:
        # print(f"{val=} {n=}")
        # https://stackoverflow.com/a/5833119
        n = val >> n
        # https://stackoverflow.com/a/37095855/4438492
        n = n & 0xFFFFFFFF
        return n | (-(n & 0x80000000))
