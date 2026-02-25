package pl.akmf.ksef.sdk.api.builders.session;

import pl.akmf.ksef.sdk.client.model.session.online.SendInvoiceOnlineSessionRequest;

public class SendInvoiceOnlineSessionRequestBuilder {
    private String invoiceHash;
    private long invoiceSize;
    private String encryptedInvoiceHash;
    private long encryptedInvoiceSize;
    private String encryptedInvoiceContent;
    private String hashOfCorrectedInvoice;
    private boolean offlineMode;

    public SendInvoiceOnlineSessionRequestBuilder withInvoiceHash(String invoiceHash) {
        this.invoiceHash = invoiceHash;
        return this;
    }

    public SendInvoiceOnlineSessionRequestBuilder withInvoiceSize(long invoiceSize) {
        this.invoiceSize = invoiceSize;
        return this;
    }

    public SendInvoiceOnlineSessionRequestBuilder withEncryptedInvoiceHash(String encryptedInvoiceHash) {
        this.encryptedInvoiceHash = encryptedInvoiceHash;
        return this;
    }

    public SendInvoiceOnlineSessionRequestBuilder withEncryptedInvoiceSize(long encryptedInvoiceSize) {
        this.encryptedInvoiceSize = encryptedInvoiceSize;
        return this;
    }

    public SendInvoiceOnlineSessionRequestBuilder withHashOfCorrectedInvoice(String hashOfCorrectedInvoice) {
        this.hashOfCorrectedInvoice = hashOfCorrectedInvoice;
        return this;
    }
    public SendInvoiceOnlineSessionRequestBuilder withOfflineMode(boolean offlineMode) {
        this.offlineMode = offlineMode;
        return this;
    }
    public SendInvoiceOnlineSessionRequestBuilder withEncryptedInvoiceContent(String encryptedInvoiceContent) {
        this.encryptedInvoiceContent = encryptedInvoiceContent;
        return this;
    }

    public SendInvoiceOnlineSessionRequest build() {
        SendInvoiceOnlineSessionRequest request = new SendInvoiceOnlineSessionRequest();
        request.setInvoiceHash(invoiceHash);
        request.setInvoiceSize(invoiceSize);
        request.setEncryptedInvoiceHash(encryptedInvoiceHash);
        request.setEncryptedInvoiceSize(encryptedInvoiceSize);
        request.setEncryptedInvoiceContent(encryptedInvoiceContent);
        request.setHashOfCorrectedInvoice(hashOfCorrectedInvoice);
        request.setOfflineMode(offlineMode);

        return request;
    }
}
