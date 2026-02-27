package pl.akmf.ksef.sdk.client.model.qrcode;

public class QrCodeResult {

    public String url;
    public String qrCode;

    public QrCodeResult() {
    }

    public QrCodeResult(String url, String qrCode) {
        this.url = url;
        this.qrCode = qrCode;
    }

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public String getQrCode() {
        return qrCode;
    }

    public void setQrCode(String qrCode) {
        this.qrCode = qrCode;
    }
}
