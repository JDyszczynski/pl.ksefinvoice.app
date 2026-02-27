package pl.akmf.ksef.sdk.client.model.session.batch;

import pl.akmf.ksef.sdk.client.model.session.EncryptionInfo;
import pl.akmf.ksef.sdk.client.model.session.FormCode;

public class OpenBatchSessionRequest {
    private FormCode formCode;
    private BatchFileInfo batchFile;
    private EncryptionInfo encryption;
    private boolean offlineMode = false;

    public OpenBatchSessionRequest() {

    }

    public OpenBatchSessionRequest(FormCode formCode, BatchFileInfo batchFile, EncryptionInfo encryption, boolean offlineMode) {
        this.formCode = formCode;
        this.batchFile = batchFile;
        this.encryption = encryption;
        this.offlineMode = offlineMode;
    }

    public FormCode getFormCode() {
        return formCode;
    }

    public void setFormCode(FormCode formCode) {
        this.formCode = formCode;
    }

    public BatchFileInfo getBatchFile() {
        return batchFile;
    }

    public void setBatchFile(BatchFileInfo batchFile) {
        this.batchFile = batchFile;
    }

    public EncryptionInfo getEncryption() {
        return encryption;
    }

    public void setEncryption(EncryptionInfo encryption) {
        this.encryption = encryption;
    }

    public boolean isOfflineMode() {
        return offlineMode;
    }

    public void setOfflineMode(boolean offlineMode) {
        this.offlineMode = offlineMode;
    }
}
