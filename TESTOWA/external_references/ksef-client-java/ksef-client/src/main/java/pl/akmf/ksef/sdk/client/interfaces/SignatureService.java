package pl.akmf.ksef.sdk.client.interfaces;

import java.io.IOException;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;

public interface SignatureService {

    String sign(byte[] xml, X509Certificate signatureCertificate, PrivateKey privateKey) throws IOException;
}
