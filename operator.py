import kopf
import logging
from kubernetes import client

@kopf.on.create('odoo')
def create_fn(body, **kwargs):
    meta = kwargs.get("meta")
    spec = kwargs.get("spec", {})
    owner_reference = _get_owner_reference(meta)
    name = spec.get("ingress").get("host")
    namespace = meta["namespace"]
    pvc = _create_filestore_pvc(namespace, owner_reference, spec, name)
    odoo_conf = _create_odoo_conf(namespace, owner_reference, spec)
    tls_cert = _create_tls_cert(namespace, owner_reference, spec, name)
    deployment = _create_deployment(namespace, owner_reference, spec, name, pvc)

# Certificate creation

def _create_tls_cert(
    namespace: str,
    owner_reference: client.V1OwnerReference,
    spec: dict,
    name: str = "odoo-tls-cert"
) -> client.V1Secret:
    # use the ingress portion of the spec
    host = name
    issuer = spec.get("ingress").get("issuer")
    apiVersion = "cert-manager.io/v1"
    kind = "Certificate"
    metadata = client.V1ObjectMeta(
        name=name,
        owner_references=[owner_reference]
    )
    cert_spec = {
        "secretName": f"{name}-cert",
        "dnsNames": [name],
        "issuerRef": {
            "name": issuer,
            "kind": "ClusterIssuer",
        }
    }
    cert_definition = {
        "apiVersion": apiVersion,
        "kind": kind,
        "metadata": metadata,
        "spec": cert_spec
    }
    cert = client.CustomObjectsApi().create_namespaced_custom_object(
        group="cert-manager.io",
        version="v1",
        namespace=namespace,
        plural="certificates",
        body=cert_definition
    )
    logging.info(f"Created certificate: {cert}")
    return cert



# Odoo.conf creation
# Odoo.conf creation

def _create_odoo_conf(
    namespace: str,
    owner_reference: client.V1OwnerReference,
    spec: dict,
) -> client.V1ConfigMap:
    metadata = client.V1ObjectMeta(
        name=f"odoo-conf",
        owner_references=[owner_reference],
    )
    admin_pw = spec.get("adminPassword", "")
    contents = f"""[options]
data_dir = /var/lib/odoo
proxy_mode = True
admin_password = {admin_pw}
"""
    additional_params = spec.get("configOptions", {})
    for key, value in additional_params.items():
        contents += f"{key} = {value}\n"
    temp_configmap = client.V1ConfigMap(
        metadata=metadata,
        data={
            "odoo.conf": contents
        }
    )
    configmap= client.CoreV1Api().create_namespaced_config_map(
        namespace=namespace,
        body=temp_configmap,
    )
    logging.info(f"Created odoo.conf: {configmap}")
    return configmap




# Deployment creation

def _create_deployment(
    namespace: str,
    owner_reference: client.V1OwnerReference,
    spec: dict,
    name: str,
    pvc: client.V1PersistentVolumeClaim
) -> client.V1Deployment:
    image = spec.get("image", "odoo:18.0")



# PVC creation

def _create_filestore_pvc(
    namespace: str,
    owner_reference: client.V1OwnerReference,
    spec: dict,
    name: str = "odoo-filestore-pvc"
) -> client.V1PersistentVolumeClaim:
    # Only use the filestore portion of the spec
    spec = spec.get("filestore", {})
    metadata = client.V1ObjectMeta(
        name=name,
        owner_references=[owner_reference]
    )
    size = spec.get("size", "2Gi")
    storage_class = spec.get("storageClass", "standard")
    pvc_spec = client.V1PersistentVolumeClaimSpec(
        access_modes=["ReadWriteOnce"],
        storage_class_name=storage_class,
        resources=client.V1ResourceRequirements(
            requests={"storage": size}
        )
    )
    temp_pvc = client.V1PersistentVolumeClaim(
        metadata=metadata,
        spec=pvc_spec,
    )
    pvc = client.CoreV1Api().create_namespaced_persistent_volume_claim(
        namespace=namespace,
        body=temp_pvc,
    )
    logging.info(f"Created filestore PVC: {pvc}")
    return pvc


# Owner reference helper 
def _get_owner_reference(meta: dict) -> client.V1OwnerReference:
    owner_reference = client.V1OwnerReference(
        api_version="odoo.bemade.org/v1",
        kind="OdooInstance",
        name=meta["name"],
        uid=meta["uid"],
        controller=True,
        block_owner_deletion=True,
    )
    return owner_reference

def _get_filestore_pvc(
    owner_reference: client.V1OwnerReference,
    spec: dict,
    name: str = "odoo-filestore-pvc"
) -> client.V1PersistentVolumeClaim:
    return pvc
