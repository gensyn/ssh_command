class HomeAssistant:
    def __init__(self):
        self.services = None
        self.data = {}


class ServiceCall:
    def __init__(self, data=None):
        self.data = data or {}


class SupportsResponse:
    ONLY = "only"
    OPTIONAL = "optional"
    NONE = "none"


ServiceResponse = dict
