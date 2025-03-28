"""
Custom webhook server implementation that uses service mode for Kubernetes webhook configurations.

This server extends Kopf's WebhookServer but yields a service configuration 
instead of a URL configuration, making it more suitable for in-cluster deployments.
"""

import os
import logging
import kopf

logger = logging.getLogger(__name__)


class ServiceModeWebhookServer(kopf.WebhookServer):
    """
    A webhook server that uses service mode for Kubernetes webhook configurations.
    
    This server extends Kopf's WebhookServer but yields a service configuration
    instead of a URL configuration. This is more suitable for in-cluster deployments
    as it allows Kubernetes to route webhook requests through the service instead
    of using a URL.
    
    The service namespace and name are configurable via environment variables:
    - POD_NAMESPACE: The namespace where the service is deployed (default: "default")
    - SERVICE_NAME: The name of the service (default: "odoo-operator-webhook")
    """
    
    async def __call__(self, fn):
        """
        Start the webhook server and yield a service configuration.
        
        This overrides the default implementation to yield a service configuration
        instead of a URL configuration.
        
        Args:
            fn: The webhook function to call when a request is received.
            
        Yields:
            dict: A service configuration for Kubernetes webhook configurations.
        """
        # Build SSL context and get CA data
        cadata, context = self._build_ssl()
        path = self.path.rstrip('/') if self.path else ''
        
        # Set up the web application
        app = self._setup_app(fn, path)
        runner = self._setup_runner(app)
        await runner.setup()
        
        try:
            # Start the server
            addr = self.addr or None
            port = self.port or self._allocate_free_port()
            site = self._setup_site(runner, addr, port, context)
            await site.start()
            
            # Log the server details
            schema = 'http' if context is None else 'https'
            listen_url = self._build_url(schema, addr or '*', port, self.path or '')
            logger.debug(f"Listening for webhooks at {listen_url}")
            
            # Create a service configuration instead of a URL configuration
            namespace = os.getenv("POD_NAMESPACE", "default")
            service_name = os.getenv("SERVICE_NAME", "odoo-operator-webhook")
            
            client_config = {
                'service': {
                    'namespace': namespace,
                    'name': service_name,
                    'path': path,
                    'port': port
                }
            }
            
            if cadata is not None:
                client_config['caBundle'] = kopf._core.engines.admission.base64.b64encode(cadata).decode('ascii')
            
            logger.info(f"Using service mode for webhook configuration: {service_name}.{namespace}")
            yield client_config
            await kopf._core.engines.admission.asyncio.Event().wait()
        finally:
            await runner.cleanup()
    
    def _setup_app(self, fn, path):
        """Set up the web application for the webhook server."""
        async def _serve_fn(request):
            return await self._serve(fn, request)
        
        app = kopf._core.engines.admission.aiohttp.web.Application()
        app.add_routes([kopf._core.engines.admission.aiohttp.web.post(f"{path}/{{id:.*}}", _serve_fn)])
        return app
    
    def _setup_runner(self, app):
        """Set up the application runner for the webhook server."""
        return kopf._core.engines.admission.aiohttp.web.AppRunner(app, handle_signals=False)
    
    def _setup_site(self, runner, addr, port, context):
        """Set up the TCP site for the webhook server."""
        return kopf._core.engines.admission.aiohttp.web.TCPSite(
            runner, addr, port, ssl_context=context, reuse_port=True
        )
