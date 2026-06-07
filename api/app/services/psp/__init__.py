from app.core.config import settings

def get_psp():
    if settings.PSP_PROVIDER == "tingg":
        from app.services.psp.tingg import TinggAdapter
        return TinggAdapter()
    from app.services.psp.mock import MockAdapter
    return MockAdapter()