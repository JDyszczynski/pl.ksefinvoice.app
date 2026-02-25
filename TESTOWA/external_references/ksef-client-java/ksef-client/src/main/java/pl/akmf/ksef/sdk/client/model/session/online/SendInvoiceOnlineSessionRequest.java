package pl.akmf.ksef.sdk.client.model.session.online;

public class SendInvoiceOnlineSessionRequest {
    private String invoiceHash;
    private long invoiceSize;
    private String encryptedInvoiceHash;
    private long encryptedInvoiceSize;
    private String encryptedInvoiceContent;
    private boolean offlineMode = false;
    private String hashOfCorrectedInvoice;

    public String getInvoiceHash() {
        return invoiceHash;
    }

    public void setInvoiceHash(String invoiceHash) {
        this.invoiceHash = invoiceHash;
    }

    public long getInvoiceSize() {
        return invoiceSize;
    }

    public void setInvoiceSize(long invoiceSize) {
        this.invoiceSize = invoiceSize;
    }

    public String getEncryptedInvoiceHash() {
        return encryptedInvoiceHash;
    }

    public void setEncryptedInvoiceHash(String encryptedInvoiceHash) {
        this.encryptedInvoiceHash = encryptedInvoiceHash;
    }

    public long getEncryptedInvoiceSize() {
        return encryptedInvoiceSize;
    }

    public void setEncryptedInvoiceSize(long encryptedInvoiceSize) {
        this.encryptedInvoiceSize = encryptedInvoiceSize;
    }

    public String getEncryptedInvoiceContent() {
        return encryptedInvoiceContent;
    }

    public void setEncryptedInvoiceContent(String encryptedInvoiceContent) {
        this.encryptedInvoiceContent = encryptedInvoiceContent;
    }

    public boolean isOfflineMode() {
        return offlineMode;
    }

    public void setOfflineMode(boolean offlineMode) {
        this.offlineMode = offlineMode;
    }

    public String getHashOfCorrectedInvoice() {
        return hashOfCorrectedInvoice;
    }

    public void setHashOfCorrectedInvoice(String hashOfCorrectedInvoice) {
        this.hashOfCorrectedInvoice = hashOfCorrectedInvoice;
    }
}
