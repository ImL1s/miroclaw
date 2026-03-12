import os
import subprocess
import grpc
import logging
import time

logger = logging.getLogger(__name__)

# Default paths, overridable via environment variables
DEFAULT_CERT_PATH = os.environ.get('CLUSTER_CERT_PATH', '.cluster.crt')
DEFAULT_KEY_PATH = os.environ.get('CLUSTER_KEY_PATH', '.cluster.key')

def generate_self_signed_cert(cert_path=None, key_path=None):
    cert_path = cert_path or DEFAULT_CERT_PATH
    key_path = key_path or DEFAULT_KEY_PATH
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        logger.info(f"TLS certificates already exist at {cert_path}")
        return
    
    # Ensure directory exists
    cert_dir = os.path.dirname(cert_path)
    if cert_dir:
        os.makedirs(cert_dir, exist_ok=True)
    
    logger.info(f"Generating self-signed cluster TLS certificates at {cert_path}...")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:4096", "-nodes",
        "-out", cert_path, "-keyout", key_path, "-days", "365",
        "-subj", "/C=US/ST=Local/L=Local/O=MiroClaw/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,DNS:coordinator,IP:127.0.0.1"
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info("TLS certificates generated successfully.")

def get_server_credentials(cert_path=None, key_path=None) -> grpc.ServerCredentials:
    cert_path = cert_path or DEFAULT_CERT_PATH
    key_path = key_path or DEFAULT_KEY_PATH
    generate_self_signed_cert(cert_path, key_path)
    with open(key_path, 'rb') as f:
        private_key = f.read()
    with open(cert_path, 'rb') as f:
        certificate_chain = f.read()
    return grpc.ssl_server_credentials([(private_key, certificate_chain)])

def get_client_credentials(cert_path=None) -> grpc.ChannelCredentials:
    cert_path = cert_path or DEFAULT_CERT_PATH
    
    # Wait for the server to generate it in a local multi-process scenario
    for i in range(60):
        if os.path.exists(cert_path):
            break
        if i % 10 == 0:
            logger.info(f"Waiting for TLS certificate at {cert_path}...")
        time.sleep(1)
    
    if not os.path.exists(cert_path):
        raise FileNotFoundError(f"TLS certificate {cert_path} not found after 60s. Ensure Coordinator is running.")
        
    with open(cert_path, 'rb') as f:
        certificate_chain = f.read()
    return grpc.ssl_channel_credentials(certificate_chain)

