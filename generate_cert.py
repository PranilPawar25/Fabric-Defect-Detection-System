#!/usr/bin/env python3
"""
Generate self-signed SSL certificate for live stream HTTPS server.

Creates a certificate valid for localhost, 127.0.0.1, and the detected LAN IP.
Regenerates automatically when the LAN IP changes (e.g., switching Wi-Fi or using phone hotspot).
"""

import os
import socket
import sys
from pathlib import Path
from datetime import datetime, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import ipaddress


def get_lan_ip():
    """
    Detect the LAN IP address using the default route interface.
    
    Uses UDP socket "connect" trick (no packet is sent) to find the local IP
    that would be used to reach a public IP.
    
    Filters out:
    - Loopback (127.x.x.x)
    - Link-local (169.254.x.x)
    - Virtual adapters (common patterns)
    
    Returns:
        str: LAN IP address or None if not found
    """
    # Try environment variable override first
    env_ip = os.environ.get('LIVE_HOST_IP')
    if env_ip:
        try:
            ipaddress.ip_address(env_ip)
            print(f"[Cert] Using override IP from LIVE_HOST_IP: {env_ip}")
            return env_ip
        except ValueError:
            print(f"[Cert] Warning: Invalid LIVE_HOST_IP '{env_ip}', auto-detecting...")
    
    # Auto-detect using default route
    try:
        # Connect to a public IP (no packet is actually sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # Validate it's not loopback or link-local
        if local_ip.startswith('127.') or local_ip.startswith('169.254.'):
            print(f"[Cert] Ignoring loopback/link-local IP: {local_ip}")
            return None
        
        print(f"[Cert] Detected LAN IP: {local_ip}")
        return local_ip
    except Exception as e:
        print(f"[Cert] Could not detect LAN IP: {e}")
        return None


def get_all_local_ips():
    """
    Get all local IP addresses for informational purposes.
    
    Returns:
        list: List of (interface_name, ip_address) tuples
    """
    ips = []
    hostname = socket.gethostname()
    
    try:
        # Get all addresses for hostname
        addr_info = socket.getaddrinfo(hostname, None)
        for addr in addr_info:
            ip = addr[4][0]
            if ':' not in ip:  # IPv4 only
                ips.append(('hostname', ip))
    except Exception:
        pass
    
    return ips


def cert_needs_regeneration(cert_path, key_path, lan_ip):
    """
    Check if the certificate needs to be regenerated.
    
    Args:
        cert_path: Path to certificate file
        key_path: Path to key file
        lan_ip: Current LAN IP address
        
    Returns:
        tuple: (needs_regen: bool, reason: str)
    """
    if not cert_path.exists() or not key_path.exists():
        return True, "Certificate files do not exist"
    
    try:
        # Load existing certificate
        with open(cert_path, 'rb') as f:
            cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        
        # Check expiration
        now = datetime.utcnow()
        if cert.not_valid_after < now:
            return True, "Certificate expired"
        
        if cert.not_valid_after < now + timedelta(days=7):
            return True, "Certificate expires within 7 days"
        
        # Check if current LAN IP is in SAN
        if lan_ip:
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                san_ips = [str(ip) for ip in san_ext.value.get_values_for_type(x509.IPAddress)]
                
                if lan_ip not in san_ips:
                    return True, f"LAN IP {lan_ip} not in certificate (has: {san_ips})"
            except x509.ExtensionNotFound:
                return True, "Certificate has no Subject Alternative Name"
        
        return False, "Certificate is valid"
        
    except Exception as e:
        return True, f"Error reading certificate: {e}"


def generate_certificate(cert_path, key_path, lan_ip):
    """
    Generate a self-signed certificate.
    
    Args:
        cert_path: Output path for certificate
        key_path: Output path for private key
        lan_ip: LAN IP address to include in SAN
    """
    print("[Cert] Generating new self-signed certificate...")
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Subject and issuer
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Local"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Fabric Defect Detection"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Fabric Live Scanner"),
    ])
    
    # Build SAN (Subject Alternative Name) list
    san_list = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]
    
    if lan_ip:
        try:
            san_list.append(x509.IPAddress(ipaddress.IPv4Address(lan_ip)))
            print(f"[Cert] Including LAN IP in certificate: {lan_ip}")
        except ValueError:
            print(f"[Cert] Warning: Invalid IP address: {lan_ip}")
    
    # Create certificate
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .sign(private_key, hashes.SHA256(), default_backend())
    )
    
    # Write private key
    with open(key_path, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Write certificate
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    print(f"[Cert] Certificate written to: {cert_path}")
    print(f"[Cert] Private key written to: {key_path}")
    print(f"[Cert] Valid until: {cert.not_valid_after.strftime('%Y-%m-%d %H:%M:%S UTC')}")


def main():
    """Main entry point."""
    # Determine paths
    script_dir = Path(__file__).parent
    certs_dir = script_dir / "certs"
    cert_path = certs_dir / "cert.pem"
    key_path = certs_dir / "key.pem"
    
    # Create certs directory if needed
    certs_dir.mkdir(exist_ok=True)
    
    # Detect LAN IP
    lan_ip = get_lan_ip()
    
    if not lan_ip:
        print("\n" + "="*70)
        print("WARNING: No LAN IP detected!")
        print("="*70)
        print("The laptop is not connected to any network.")
        print("Options:")
        print("  1. Connect to Wi-Fi and run this script again")
        print("  2. Use your phone's hotspot and run this script again")
        print("  3. Set LIVE_HOST_IP environment variable manually")
        print("\nGenerating certificate for localhost only...")
        print("="*70 + "\n")
    
    # Show all detected IPs for debugging
    all_ips = get_all_local_ips()
    if all_ips:
        print("\n[Cert] All local IP addresses detected:")
        for name, ip in all_ips:
            print(f"       - {ip} ({name})")
        print()
    
    # Check if regeneration is needed
    needs_regen, reason = cert_needs_regeneration(cert_path, key_path, lan_ip)
    
    if needs_regen:
        print(f"[Cert] Regeneration needed: {reason}")
        generate_certificate(cert_path, key_path, lan_ip)
        print("[Cert] ✓ Certificate generation complete")
    else:
        print(f"[Cert] ✓ Existing certificate is valid: {reason}")
    
    return 0 if lan_ip else 1


if __name__ == "__main__":
    sys.exit(main())
