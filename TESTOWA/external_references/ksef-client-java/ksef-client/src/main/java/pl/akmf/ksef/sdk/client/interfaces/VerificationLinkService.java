package pl.akmf.ksef.sdk.client.interfaces;

import pl.akmf.ksef.sdk.client.model.qrcode.ContextIdentifierType;

import java.security.PrivateKey;
import java.time.LocalDate;

public interface VerificationLinkService {

    /**
     * Buduje link do weryfikacji faktury w systemie KSeF.
     *
     * @param nip
     * @param issueDate
     * @param invoiceHash
     * @return
     */
    String buildInvoiceVerificationUrl(String nip, LocalDate issueDate, String invoiceHash);

    /**
     * Buduje link do weryfikacji certyfikatu Wystawcy (offline).
     *
     * @param sellerNip
     * @param contextIdentifierType
     * @param contextIdentifierValue
     * @param certificateSerial
     * @param invoiceHash
     * @param privateKey
     * @return
     */
    String buildCertificateVerificationUrl(String sellerNip, ContextIdentifierType contextIdentifierType, String contextIdentifierValue, String certificateSerial, String invoiceHash, PrivateKey privateKey);
}
