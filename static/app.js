/* ============================================================
   Shared helpers used by every page.
   ============================================================ */

const ZKT = {

    apiKey: document
        .querySelector('meta[name="api-key"]')
        .getAttribute("content"),

    async apiFetch(path, options) {

        options = options || {};

        const headers = Object.assign(
            {},
            options.headers || {},
            { "X-API-Key": ZKT.apiKey }
        );

        const response = await fetch(path, Object.assign({}, options, { headers }));

        if (!response.ok) {

            let message = `Request failed (${response.status})`;

            try {
                const body = await response.json();
                if (body && body.message) {
                    message = body.message;
                }
            } catch (err) {
                /* response wasn't JSON - keep default message */
            }

            throw new Error(message);
        }

        return response;
    },

    async apiJson(path, options) {
        const response = await ZKT.apiFetch(path, options);
        return response.json();
    },

    escapeHtml(value) {

        if (value === null || value === undefined) {
            return "";
        }

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    },

    debounce(fn, wait) {

        let timer = null;

        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), wait);
        };
    },

    punchBadgeClass(punchType) {

        if (!punchType) return "badge-other";

        const value = punchType.toLowerCase();

        if (value.includes("in") && !value.includes("break") && !value.includes("overtime")) {
            return "badge-in";
        }

        if (value.includes("out") && !value.includes("break") && !value.includes("overtime")) {
            return "badge-out";
        }

        if (value.includes("break")) {
            return "badge-break";
        }

        return "badge-other";
    },

};
