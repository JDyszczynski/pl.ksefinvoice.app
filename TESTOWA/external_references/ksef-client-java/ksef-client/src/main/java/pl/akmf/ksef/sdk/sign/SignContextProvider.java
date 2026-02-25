package pl.akmf.ksef.sdk.sign;

import eu.europa.esig.dss.model.SignatureValue;
import eu.europa.esig.dss.model.ToBeSigned;

import java.security.PrivateKey;
import java.security.cert.X509Certificate;

public interface SignContextProvider {

    SignatureValue createSignatureValue(ToBeSigned toBeSigned, X509Certificate signatureCertificate, PrivateKey privateKey);
}
