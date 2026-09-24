(function () {
  const params = new URLSearchParams(window.location.search);
  const step = params.get("step") || "overview";
  document.body.setAttribute("data-step", step);
  document.querySelectorAll(".steps a").forEach(function (link) {
    link.classList.toggle("active", link.getAttribute("data-step") === step);
  });
  const captions = {
    overview:
      "Website URL https://intellixcrm.com matches this web app. Sandbox environment.",
    "login-kit":
      "Login Kit: user clicks Connect TikTok. OAuth v2 authorize, one token per brand.",
    scopes:
      "Scopes used: user.info.basic (profile) and video.publish (Content Posting API). No unused scopes.",
    composer:
      "User interface: choose brand Coins Marocain, attach an MP4, write a caption.",
    publish:
      "Content Posting API Direct Post FILE_UPLOAD. Sandbox privacy SELF_ONLY.",
    status:
      "Status poll /v2/post/publish/status/fetch/ until PUBLISH_COMPLETE.",
  };
  const caption = document.getElementById("caption");
  if (caption && captions[step]) caption.textContent = captions[step];
})();
