(function (global) {
  var API = "/partner-api";

  function req(method, path, body, token) {
    var opts = {
      method: method,
      headers: { Accept: "application/json" },
    };
    if (token) opts.headers.Authorization = "Bearer " + token;
    if (body != null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(API + path, opts).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) {
          var err = new Error((j && j.error) || "http_" + r.status);
          err.payload = j;
          throw err;
        }
        return j;
      });
    });
  }

  function tokenFromUrl() {
    try {
      return new URLSearchParams(location.search).get("token") || "";
    } catch (e) {
      return "";
    }
  }

  function rememberToken(token) {
    if (!token) return;
    try {
      sessionStorage.setItem("cm_partner_token", token);
    } catch (e) {}
  }

  function currentToken() {
    var t = tokenFromUrl();
    if (t) {
      rememberToken(t);
      return t;
    }
    try {
      return sessionStorage.getItem("cm_partner_token") || "";
    } catch (e2) {
      return "";
    }
  }

  global.CMPartner = {
    get: function (path, token) {
      return req("GET", path, null, token);
    },
    post: function (path, body, token) {
      return req("POST", path, body, token);
    },
    put: function (path, body, token) {
      return req("PUT", path, body, token);
    },
    tokenFromUrl: tokenFromUrl,
    currentToken: currentToken,
    rememberToken: rememberToken,
    session: function (token) {
      var t = token || currentToken();
      return req("GET", "/session?token=" + encodeURIComponent(t), null, t);
    },
    listings: function () {
      return req("GET", "/public/listings");
    },
    upload: function (file, kind, token) {
      var t = token || currentToken();
      var fd = new FormData();
      fd.append("file", file);
      fd.append("kind", kind || "photo");
      if (t) fd.append("token", t);
      return fetch(API + "/merchant/upload", {
        method: "POST",
        headers: t
          ? { Authorization: "Bearer " + t, Accept: "application/json" }
          : { Accept: "application/json" },
        body: fd,
      }).then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok) {
            var err = new Error((j && j.error) || "http_" + r.status);
            err.payload = j;
            throw err;
          }
          return j;
        });
      });
    },
  };
})(window);
