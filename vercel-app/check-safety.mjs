const BASE = "https://pr.prachiadmane.com";

async function main() {
  const login = await fetch(`${BASE}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: "gpBE6WPWv9RxBUs-6ZbFacnZA1Toa0ty" }),
  });
  const cookie = (login.headers.getSetCookie?.() || []).map((c) => c.split(";")[0]).join("; ");
  const tok = await fetch(`${BASE}/api/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: BASE, Cookie: cookie },
    body: "{}",
  }).then((r) => r.json());

  const post = async (action, extra) => {
    const res = await fetch(`${BASE}/api/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: BASE,
        Cookie: cookie,
        Authorization: `Bearer ${tok.token}`,
      },
      body: JSON.stringify({ action, ...extra }),
    });
    return { status: res.status, body: await res.text() };
  };

  const bad = await post("analyze", { article_url: "javascript:alert(1)" });
  console.log("bad-url:", bad.status, bad.body.slice(0, 120));

  const bad2 = await post("analyze", { article_url: "https://trusted.com@evil.example/" });
  console.log("userinfo-trick:", bad2.status, bad2.body.slice(0, 120));

  const usage = await fetch(`${BASE}/api/analyze`, { headers: { Cookie: cookie } }).then((r) => r.json());
  console.log("quota:", JSON.stringify(usage));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
