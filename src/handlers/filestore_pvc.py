from kubernetes import client
from .pvc_handler import PVCHandler


class FilestorePVC(PVCHandler):
    """Manages the Odoo filestore Persistent Volume Claim."""

    def __init__(self, handler):
        super().__init__(
            handler=handler,
            pvc_name_suffix="filestore-pvc",
            default_size=handler.defaults.get("filestoreSize", "2Gi"),
            default_storage_class=handler.defaults.get("storageClass", "standard"),
        )
        self.defaults = handler.defaults

    def _get_resource_body(self):
        """Get the PVC definition for the filestore."""
        spec = self.spec.get("filestore", {})
        size = spec.get("size", self.default_size)
        storage_class = spec.get("storageClass", self.default_storage_class)

        metadata = client.V1ObjectMeta(
            name=self._get_pvc_name(),
            owner_references=[self.owner_reference],
        )
        return client.V1PersistentVolumeClaim(
            metadata=metadata,
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                storage_class_name=storage_class,
                resources=client.V1ResourceRequirements(requests={"storage": size}),
            ),
        )
