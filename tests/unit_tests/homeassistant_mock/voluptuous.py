class _Marker:
    def __init__(self, key, *args, **kwargs):
        self._key = key

    def __hash__(self):
        return hash(self._key)

    def __eq__(self, other):
        return self._key == (other._key if isinstance(other, _Marker) else other)


class Required(_Marker):
    pass


class Optional(_Marker):
    pass


class Schema:
    def __init__(self, schema=None):
        pass

    def __call__(self, data):
        return data


def All(*args):
    return args[-1] if args else {}
