package pl.akmf.ksef.sdk.client.model.invoice;

public class AuthorizedSubject {
    private String nip;
    private String name;
    private int role;

    public AuthorizedSubject() {

    }

    public String getNip() {
        return nip;
    }

    public void setNip(String nip) {
        this.nip = nip;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getRole() {
        return role;
    }

    public void setRole(int role) {
        this.role = role;
    }
}
