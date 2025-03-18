import kopf
from handlers import OdooHandler


@kopf.on.create("odooinstance")
def create_fn(body, **kwargs):
    handler = OdooHandler(body, **kwargs)
    handler.on_create()


@kopf.on.update("odooinstance")
def update_fn(body, **kwargs):
    handler = OdooHandler(body, **kwargs)
    handler.on_update()


@kopf.on.delete("odooinstance")
def delete_fn(body, **kwargs):
    handler = OdooHandler(body, **kwargs)
    handler.on_delete()
