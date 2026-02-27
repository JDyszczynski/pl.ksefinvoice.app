package pl.akmf.ksef.sdk.client.model.session.batch;

import java.net.URI;
import java.util.Map;

public class PackagePartSignatureInitResponseType {
    private String method;
    private int ordinalNumber;
    private URI url;
    private Map<String, String> headers;

    public PackagePartSignatureInitResponseType() {

    }

    public PackagePartSignatureInitResponseType(String method, int ordinalNumber, URI url, Map<String, String> headers) {
        this.method = method;
        this.ordinalNumber = ordinalNumber;
        this.url = url;
        this.headers = headers;
    }

    public String getMethod() {
        return method;
    }

    public void setMethod(String method) {
        this.method = method;
    }

    public int getOrdinalNumber() {
        return ordinalNumber;
    }

    public void setOrdinalNumber(int ordinalNumber) {
        this.ordinalNumber = ordinalNumber;
    }

    public URI getUrl() {
        return url;
    }

    public void setUrl(URI url) {
        this.url = url;
    }

    public Map<String, String> getHeaders() {
        return headers;
    }

    public void setHeaders(Map<String, String> headers) {
        this.headers = headers;
    }
}
