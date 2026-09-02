(() => {

    const PER_PAGE = 50;

    const state = {
        page: 1,
        totalPages: 1,
        sortBy: "attendance_time",
        sortDir: "desc",
    };

    const els = {
        tableBody: document.getElementById("table-body"),
        errorSlot: document.getElementById("error-slot"),
        paginationInfo: document.getElementById("pagination-info"),
        pageIndicator: document.getElementById("page-indicator"),
        prevBtn: document.getElementById("prev-page"),
        nextBtn: document.getElementById("next-page"),
        exportBtn: document.getElementById("export-btn"),
        clearBtn: document.getElementById("clear-filters"),
        form: document.getElementById("filter-form"),
    };

    // ============================================================
    // FILTERS -> QUERY STRING
    // ============================================================

    function currentFilters() {

        const data = new FormData(els.form);
        const params = new URLSearchParams();

        for (const [key, value] of data.entries()) {
            if (value) params.set(key, value);
        }

        params.set("sort_by", state.sortBy);
        params.set("sort_dir", state.sortDir);

        return params;
    }

    // ============================================================
    // STATS
    // ============================================================

    async function loadStats() {

        try {

            const stats = await ZKT.apiJson("/api/v1/stats");

            document.getElementById("stat-total").textContent =
                stats.total_records.toLocaleString();

            document.getElementById("stat-today").textContent =
                stats.records_today.toLocaleString();

            document.getElementById("stat-employees").textContent =
                stats.unique_employees.toLocaleString();

            document.getElementById("stat-devices").textContent =
                `${stats.active_devices} / ${stats.total_devices}`;

        } catch (err) {
            // Stat cards are non-critical - fail silently, table still works.
        }
    }

    // ============================================================
    // FILTER DROPDOWNS
    // ============================================================

    async function loadFilterOptions() {

        try {

            const options = await ZKT.apiJson("/api/v1/attendance/filters");

            fillSelect("f-branch", options.branches);
            fillSelect("f-punch_type", options.punch_types);
            fillSelect("f-device_ip", options.device_ips);

        } catch (err) {
            // Non-critical - filters just won't have dropdown values yet.
        }
    }

    function fillSelect(id, values) {

        const select = document.getElementById(id);
        const current = select.value;

        select.innerHTML = '<option value="">All</option>' + values
            .map((v) => `<option value="${ZKT.escapeHtml(v)}">${ZKT.escapeHtml(v)}</option>`)
            .join("");

        select.value = current;
    }

    // ============================================================
    // TABLE
    // ============================================================

    function renderRows(records) {

        if (!records.length) {

            els.tableBody.innerHTML =
                '<tr><td colspan="7" class="empty-state">No attendance records match these filters.</td></tr>';

            return;
        }

        els.tableBody.innerHTML = records.map((r) => `
            <tr>
                <td class="cell-muted">
                    <a class="row-link" href="/record/${r.id}">#${r.id}</a>
                </td>
                <td>${ZKT.escapeHtml(r.attendance_time || "-")}</td>
                <td>
                    <div class="cell-name">${ZKT.escapeHtml(r.user_name || "Unknown")}</div>
                    <div class="cell-muted">ID ${ZKT.escapeHtml(r.user_id)}</div>
                </td>
                <td><span class="badge ${ZKT.punchBadgeClass(r.punch_type)}">${ZKT.escapeHtml(r.punch_type || "-")}</span></td>
                <td>${ZKT.escapeHtml(r.branch_name || "-")}</td>
                <td class="cell-muted">${ZKT.escapeHtml(r.device_ip || "-")}</td>
                <td class="cell-muted">${ZKT.escapeHtml(r.serial_number || "-")}</td>
            </tr>
        `).join("");
    }

    function renderSortIndicators() {

        document.querySelectorAll("th.sortable").forEach((th) => {

            const isActive = th.dataset.sort === state.sortBy;

            th.classList.toggle("sort-active", isActive);

            const arrow = th.querySelector(".sort-arrow");
            arrow.innerHTML = isActive
                ? (state.sortDir === "asc" ? "&#9652;" : "&#9662;")
                : "&#9662;";
        });
    }

    async function loadPage() {

        els.errorSlot.innerHTML = "";

        const wasEmpty = els.tableBody.children.length === 0;

        if (!wasEmpty) {
            els.tableBody.style.opacity = "0.5";
        }

        const params = currentFilters();
        params.set("page", state.page);
        params.set("per_page", PER_PAGE);

        try {

            const data = await ZKT.apiJson(`/api/v1/attendance?${params.toString()}`);

            state.totalPages = data.total_pages || 1;

            renderRows(data.data);

            const start = data.count === 0 ? 0 : (data.page - 1) * data.per_page + 1;
            const end = Math.min(data.page * data.per_page, data.count);

            els.paginationInfo.textContent =
                `Showing ${start.toLocaleString()}-${end.toLocaleString()} of ${data.count.toLocaleString()}`;

            els.pageIndicator.textContent = `${data.page} / ${Math.max(state.totalPages, 1)}`;

            els.prevBtn.disabled = !data.previous;
            els.nextBtn.disabled = !data.next;

        } catch (err) {

            els.errorSlot.innerHTML =
                `<div class="error-banner">Could not load attendance data: ${ZKT.escapeHtml(err.message)}</div>`;

            els.tableBody.innerHTML =
                '<tr><td colspan="7" class="empty-state">Failed to load.</td></tr>';

        } finally {
            els.tableBody.style.opacity = "1";
        }
    }

    // ============================================================
    // EVENTS
    // ============================================================

    const debouncedReload = ZKT.debounce(() => {
        state.page = 1;
        loadPage();
    }, 350);

    els.form.addEventListener("input", debouncedReload);
    els.form.addEventListener("change", debouncedReload);

    els.clearBtn.addEventListener("click", () => {
        els.form.reset();
        state.page = 1;
        loadPage();
    });

    els.prevBtn.addEventListener("click", () => {
        if (state.page > 1) {
            state.page -= 1;
            loadPage();
        }
    });

    els.nextBtn.addEventListener("click", () => {
        if (state.page < state.totalPages) {
            state.page += 1;
            loadPage();
        }
    });

    document.querySelectorAll("th.sortable").forEach((th) => {

        th.addEventListener("click", () => {

            const column = th.dataset.sort;

            if (state.sortBy === column) {
                state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
            } else {
                state.sortBy = column;
                state.sortDir = "desc";
            }

            renderSortIndicators();
            state.page = 1;
            loadPage();
        });
    });

    els.exportBtn.addEventListener("click", async () => {

        els.exportBtn.disabled = true;
        els.exportBtn.textContent = "Exporting…";

        try {

            const params = currentFilters();
            const response = await ZKT.apiFetch(`/api/v1/attendance/export.csv?${params.toString()}`);
            const blob = await response.blob();

            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "zkteco_attendance.csv";
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);

        } catch (err) {

            els.errorSlot.innerHTML =
                `<div class="error-banner">Export failed: ${ZKT.escapeHtml(err.message)}</div>`;

        } finally {

            els.exportBtn.disabled = false;
            els.exportBtn.textContent = "Export CSV";
        }
    });

    // ============================================================
    // INIT
    // ============================================================

    renderSortIndicators();
    loadStats();
    loadFilterOptions();
    loadPage();

})();
