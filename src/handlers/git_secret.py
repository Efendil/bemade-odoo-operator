from kubernetes import client
from .resource_handler import ResourceHandler, update_if_exists, create_if_missing
from typing import cast


class GitSecret(ResourceHandler):
    """Manages the git secret for Odoo."""

    def __init__(self, handler):
        super().__init__(handler)
        self.operator_ns = handler.operator_ns

    def _read_resource(self):
        if not self.secret_name:
            return None
        return client.CoreV1Api().read_namespaced_secret(
            name=self.secret_name,
            namespace=self.namespace,
        )

    @property
    def secret_name(self):
        return self.spec.get("gitProject", {}).get("sshSecret")

    @update_if_exists
    def handle_create(self):
        if self.secret_name:
            secret = self._get_resource_body()
            self._resource = client.CoreV1Api().create_namespaced_secret(
                namespace=self.namespace,
                body=secret,
            )

    def _get_resource_body(self):
        orig_secret = client.CoreV1Api().read_namespaced_secret(
            name=self.secret_name,
            namespace=self.operator_ns,
        )
        orig_secret = cast(client.V1Secret, orig_secret)

        return client.V1Secret(
            metadata=client.V1ObjectMeta(
                name=self.secret_name,
                owner_references=[self.owner_reference],
            ),
            type="kubernetes.io/dockerconfigjson",
            data=orig_secret.data,
        )
