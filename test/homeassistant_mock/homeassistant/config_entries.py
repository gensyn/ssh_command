class ConfigEntry:
    pass


ConfigFlowResult = dict


class ConfigFlow:
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if domain is not None:
            cls.DOMAIN = domain

    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def _async_current_entries(self):
        return []
