import base64
import uuid
import hashlib
from datetime import datetime
from lxml import etree
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding, utils
from cryptography import x509
import logging

logger = logging.getLogger(__name__)

NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"
NS_MAP = {
    "ds": NS_DS,
    "xades": NS_XADES
}

def sign_xades_bes(xml_root_element, private_key, cert_byte_data):
    """
    Podpisuje element XML formatem XAdES-BES (Enveloped).
    Tworzy strukturę <ds:Signature> wewnątrz xml_root_element.
    """
    
    # 1. Prepare Identifiers
    signature_id = f"Signature-{uuid.uuid4()}"
    signed_props_id = f"SignedProperties-{uuid.uuid4()}"
    
    # Load cert object
    cert = x509.load_pem_x509_certificate(cert_byte_data)
    
    # 2. Determine Algorithms
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        sign_alg_method = "http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"
        digest_alg = hashes.SHA256()
        key_type = "EC"
    elif isinstance(private_key, rsa.RSAPrivateKey):
        sign_alg_method = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
        digest_alg = hashes.SHA256()
        key_type = "RSA"
    else:
        raise ValueError("Unsupported key type")

    c14n_method = "http://www.w3.org/2001/10/xml-exc-c14n#"
    digest_method = "http://www.w3.org/2001/04/xmlenc#sha256"

    # 3. Create Signature Element
    signature = etree.Element(f"{{{NS_DS}}}Signature", nsmap={"ds": NS_DS}, Id=signature_id)
    xml_root_element.append(signature)

    # 4. Create SignedInfo
    signed_info = etree.SubElement(signature, f"{{{NS_DS}}}SignedInfo")
    
    # CanonicalizationMethod
    etree.SubElement(signed_info, f"{{{NS_DS}}}CanonicalizationMethod", Algorithm=c14n_method)
    
    # SignatureMethod
    etree.SubElement(signed_info, f"{{{NS_DS}}}SignatureMethod", Algorithm=sign_alg_method)
    
    # --- Reference 1: The Document (Root) ---
    ref_doc = etree.SubElement(signed_info, f"{{{NS_DS}}}Reference", URI="")
    transforms = etree.SubElement(ref_doc, f"{{{NS_DS}}}Transforms")
    etree.SubElement(transforms, f"{{{NS_DS}}}Transform", Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
    etree.SubElement(transforms, f"{{{NS_DS}}}Transform", Algorithm=c14n_method) # Usually c14n is part of transforms
    
    etree.SubElement(ref_doc, f"{{{NS_DS}}}DigestMethod", Algorithm=digest_method)
    
    # Calculate Digest of the Root Element (without Signature)
    # To do this correctly, we must serialize the root element *as if* the Signature wasn't there yet?
    # Enveloped signature transform says "remove the signature element".
    # So we serialize the root element but exclude the Signature node we just added.
    # Actually, we can temporarily remove it or make a copy.
    
    # Easier: Serialize the root (without signature appended yet) or use lxml to handle exclusion? 
    # Manual approach:
    # We appended 'signature' to 'xml_root_element'.
    # We remove it, canonicalize, hash, put it back.
    xml_root_element.remove(signature)
    
    # Canonicalize Root
    # IMPORTANT: Ensure inclusive/exclusive namespaces are handled correctly.
    # Exclusive C14N is standard.
    canonicalized_doc = etree.tostring(xml_root_element, method="c14n", exclusive=True, with_comments=False)
    
    # Hash
    hasher = hashlib.sha256()
    hasher.update(canonicalized_doc)
    doc_digest = base64.b64encode(hasher.digest()).decode()
    
    # Put signature back
    xml_root_element.append(signature)
    
    etree.SubElement(ref_doc, f"{{{NS_DS}}}DigestValue").text = doc_digest


    # Create Object container (Detached initially to control order)
    # Define namespaces explicitly to ensure consistency during C14N and final serialization
    ds_object = etree.Element(f"{{{NS_DS}}}Object", nsmap={"ds": NS_DS, "xades": NS_XADES})
    
    # QualifyingProperties
    qp = etree.SubElement(ds_object, f"{{{NS_XADES}}}QualifyingProperties", Target=f"#{signature_id}")
    
    # SignedProperties
    sp = etree.SubElement(qp, f"{{{NS_XADES}}}SignedProperties", Id=signed_props_id)
    
    # SignedSignatureProperties
    ssp = etree.SubElement(sp, f"{{{NS_XADES}}}SignedSignatureProperties")
    
    # SigningTime
    signing_time = etree.SubElement(ssp, f"{{{NS_XADES}}}SigningTime")
    signing_time.text = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # SigningCertificate
    signing_cert = etree.SubElement(ssp, f"{{{NS_XADES}}}SigningCertificate")
    cert_el = etree.SubElement(signing_cert, f"{{{NS_XADES}}}Cert")
    
    # CertDigest
    cert_digest_el = etree.SubElement(cert_el, f"{{{NS_XADES}}}CertDigest")
    etree.SubElement(cert_digest_el, f"{{{NS_DS}}}DigestMethod", Algorithm=digest_method)
    
    # Calc Cert SHA256
    cert_hasher = hashlib.sha256()
    cert_hasher.update(cert.public_bytes(serialization.Encoding.DER))
    cert_digest_val = base64.b64encode(cert_hasher.digest()).decode()
    
    etree.SubElement(cert_digest_el, f"{{{NS_DS}}}DigestValue").text = cert_digest_val
    
    # IssuerSerial
    issuer_serial_el = etree.SubElement(cert_el, f"{{{NS_XADES}}}IssuerSerial")
    
    # RFC 2253 Issuer DN
    # This can be tricky. Lxml/Cryptography might produce different formats.
    # KSeF expects specific format. 
    # Usually `cert.issuer.rfc4514_string()`
    issuer_name_str = cert.issuer.rfc4514_string()
    etree.SubElement(issuer_serial_el, f"{{{NS_DS}}}X509IssuerName").text = issuer_name_str
    
    etree.SubElement(issuer_serial_el, f"{{{NS_DS}}}X509SerialNumber").text = str(cert.serial_number)
    
    
    # Now create Reference 2 in SignedInfo
    ref_props = etree.SubElement(signed_info, f"{{{NS_DS}}}Reference", URI=f"#{signed_props_id}", Type="http://uri.etsi.org/01903#SignedProperties")
    
    # Transforms for SignedProperties (usually just C14N)
    # Actually, XAdES spec says SignedProperties are signed directly after C14N.
    # But as it is a Reference, we probably need a Transform?
    # Usually: No transform if it's same-document ID ref? 
    # Wait, usually we need Exclusive C14N transform for robustness.
    ref_props_transforms = etree.SubElement(ref_props, f"{{{NS_DS}}}Transforms")
    etree.SubElement(ref_props_transforms, f"{{{NS_DS}}}Transform", Algorithm=c14n_method)

    etree.SubElement(ref_props, f"{{{NS_DS}}}DigestMethod", Algorithm=digest_method)
    
    # Calculate Digest of SignedProperties
    # Extract the element
    # We verify the element is 'sp'
    # Canonicalize 'sp'
    # Important: 'sp' is inside the tree, so namespaces from ancestors (like xades prefix) must be preserved.
    # lxml c14n handles this if we pass the node.
    
    # Temporarily append ds_object to signature (or a dummy root) to ensure namespace context is full?
    # No, we defined nsmap on ds_object, so sp should be fine.
    
    canonicalized_sp = etree.tostring(sp, method="c14n", exclusive=True, with_comments=False)
    
    # Debug: Check canonicalized SP to ensure namespaces are correct
    # logger.info(f"Canonicalized SP: {canonicalized_sp}")
    
    sp_hasher = hashlib.sha256()
    sp_hasher.update(canonicalized_sp)
    sp_digest = base64.b64encode(sp_hasher.digest()).decode()
    
    etree.SubElement(ref_props, f"{{{NS_DS}}}DigestValue").text = sp_digest
    
    
    # 5. Sign SignedInfo
    # Canonicalize SignedInfo
    canonicalized_si = etree.tostring(signed_info, method="c14n", exclusive=True, with_comments=False)
    
    # Calculate Signature Value
    if key_type == "EC":
        signature_der = private_key.sign(
            canonicalized_si,
            ec.ECDSA(digest_alg)
        )
        # Convert DER to Raw (r|s)
        r, s = utils.decode_dss_signature(signature_der)
        # Calculate curve key size (bytes)
        # SECP256R1 -> 32 bytes
        key_size_bytes = private_key.curve.key_size // 8
        r_bytes = r.to_bytes(key_size_bytes, 'big')
        s_bytes = s.to_bytes(key_size_bytes, 'big')
        signature_bytes = r_bytes + s_bytes
        
    else: # RSA
        signature_bytes = private_key.sign(
            canonicalized_si,
            padding.PKCS1v15(),
            digest_alg
        )
        
    signature_b64 = base64.b64encode(signature_bytes).decode()
    
    etree.SubElement(signature, f"{{{NS_DS}}}SignatureValue").text = signature_b64
    
    
    # 6. KeyInfo
    key_info = etree.SubElement(signature, f"{{{NS_DS}}}KeyInfo")
    x509_data = etree.SubElement(key_info, f"{{{NS_DS}}}X509Data")
    x509_cert_el = etree.SubElement(x509_data, f"{{{NS_DS}}}X509Certificate")
    
    # PEM body without headers
    pem_str = cert.public_bytes(serialization.Encoding.PEM).decode()
    pem_lines = pem_str.strip().splitlines()
    # Remove -----BEGIN... and -----END...
    pem_body = "".join(pem_lines[1:-1])
    
    x509_cert_el.text = pem_body
    
    # 7. Append Object (Must be last in Sequence)
    signature.append(ds_object)

    return xml_root_element
