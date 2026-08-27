"use strict";

// Preserve root-relative navigation when legacy category pages are opened directly from disk.
if (window.location.protocol === "file:") {
    document.addEventListener("click", (event) => {
        const link = event.target.closest("a[href^='/']");
        if (link) {
            event.preventDefault();
            window.location.href = `http://127.0.0.1:5000${link.getAttribute("href")}`;
        }
    });
}

