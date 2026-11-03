/**
 * Nobeth Document Intelligence
 * Official Frontend Application Engine
 * Nobeth Analytics
 */

document.addEventListener("DOMContentLoaded", () => {
  // Application State
  const state = {
    currentJobId: null,
    currentJobData: null,
    currentResult: null,
    currentPageNumber: 1,
    currentVersion: "cleaned", // "verbatim" | "cleaned"
    currentStyle: "professional", // "professional" | "layout"
    zoomScale: 1.0,
    hasUnsavedChanges: false,
    dirtyBlocks: new Map(), // blockId -> { verbatim_text, cleaned_text }
    activeTimerInterval: null,
    processingStartTime: null,
    pollInterval: null,
  };

  // DOM Elements
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const btnBrowse = document.getElementById("btnBrowse");
  const uploadSection = document.getElementById("uploadSection");
  const queueContainer = document.getElementById("queueContainer");
  const queueList = document.getElementById("queueList");
  const queueCount = document.getElementById("queueCount");
  const btnClearQueue = document.getElementById("btnClearQueue");

  const processingSection = document.getElementById("processingSection");
  const procFileName = document.getElementById("procFileName");
  const procStageLabel = document.getElementById("procStageLabel");
  const procTimer = document.getElementById("procTimer");
  const progressBarFill = document.getElementById("progressBarFill");
  const pipelineSteps = document.getElementById("pipelineSteps");

  const resultSection = document.getElementById("resultSection");
  const btnBackToUpload = document.getElementById("btnBackToUpload");
  const docTitleInput = document.getElementById("docTitleInput");
  const badgeDocType = document.getElementById("badgeDocType");
  const badgeDocLang = document.getElementById("badgeDocLang");
  const badgeModelUsed = document.getElementById("badgeModelUsed");
  const badgeUncertainties = document.getElementById("badgeUncertainties");
  const badgeEdited = document.getElementById("badgeEdited");

  const sourceImage = document.getElementById("sourceImage");
  const sourceCanvasWrapper = document.getElementById("sourceCanvasWrapper");
  const bboxOverlay = document.getElementById("bboxOverlay");
  const pageIndicator = document.getElementById("pageIndicator");
  const btnPrevPage = document.getElementById("btnPrevPage");
  const btnNextPage = document.getElementById("btnNextPage");
  const btnZoomIn = document.getElementById("btnZoomIn");
  const btnZoomOut = document.getElementById("btnZoomOut");
  const btnZoomReset = document.getElementById("btnZoomReset");
  const zoomLevel = document.getElementById("zoomLevel");

  const tabCleaned = document.getElementById("tabCleaned");
  const tabVerbatim = document.getElementById("tabVerbatim");
  const btnStyleProfessional = document.getElementById("btnStyleProfessional");
  const btnStyleLayout = document.getElementById("btnStyleLayout");
  const btnSaveEdits = document.getElementById("btnSaveEdits");
  const btnRestoreOriginal = document.getElementById("btnRestoreOriginal");
  const btnRegenerateCleaned = document.getElementById("btnRegenerateCleaned");
  const uncertaintyBar = document.getElementById("uncertaintyBar");
  const uncMessage = document.getElementById("uncMessage");
  const documentCanvas = document.getElementById("documentCanvas");

  const btnExportMenu = document.getElementById("btnExportMenu");
  const exportDropdownMenu = document.getElementById("exportDropdownMenu");
  const btnPrint = document.getElementById("btnPrint");

  const settingsModal = document.getElementById("settingsModal");
  const btnOpenSettings = document.getElementById("btnOpenSettings");
  const btnCloseSettingsModal = document.getElementById("btnCloseSettingsModal");
  const btnCloseSettingsBtn = document.getElementById("btnCloseSettingsBtn");

  const toastContainer = document.getElementById("toastContainer");

  // =========================================================================
  // TOAST NOTIFICATIONS
  // =========================================================================
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 200);
    }, 4000);
  }

  // =========================================================================
  // DRAG & DROP AND FILE UPLOAD
  // =========================================================================
  btnBrowse.addEventListener("click", () => fileInput.click());

  dropzone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesUpload(e.dataTransfer.files);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFilesUpload(e.target.files);
    }
  });

  async function handleFilesUpload(fileList) {
    const allowed = ["jpg", "jpeg", "png", "pdf", "docx"];
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      const ext = file.name.split(".").pop().toLowerCase();
      if (!allowed.includes(ext)) {
        showToast(`File "${file.name}" has an unsupported format.`, "error");
        continue;
      }
      if (file.size > 25 * 1024 * 1024) {
        showToast(`File "${file.name}" exceeds 25 MB limit.`, "error");
        continue;
      }

      await uploadSingleFile(file);
    }
    fileInput.value = "";
    loadQueue();
  }

  async function uploadSingleFile(file) {
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.detail || "Upload failed.", "error");
        return;
      }

      showToast(`Uploaded "${file.name}". Starting processing...`, "success");
      // Start tracking this job
      trackJob(data.job_id, file.name);
    } catch (err) {
      showToast(`Network error uploading "${file.name}".`, "error");
    }
  }

  // =========================================================================
  // QUEUE MANAGEMENT
  // =========================================================================
  async function loadQueue() {
    try {
      const res = await fetch("/api/jobs");
      if (!res.ok) return;
      const jobs = await res.json();

      queueCount.textContent = jobs.length;
      if (jobs.length > 0) {
        queueContainer.style.display = "block";
        renderQueue(jobs);
      } else {
        queueContainer.style.display = "none";
      }
    } catch (e) {
      console.warn("Could not refresh queue:", e);
    }
  }

  function renderQueue(jobs) {
    queueList.innerHTML = "";
    jobs.forEach((job) => {
      const item = document.createElement("div");
      item.className = "queue-item";

      const sizeKb = Math.round(job.file_size_bytes / 1024);
      let statusColor = "#64748B";
      if (job.status === "ready") statusColor = "var(--accent-green)";
      else if (job.status === "failed") statusColor = "var(--accent-red)";
      else statusColor = "var(--accent-amber)";

      item.innerHTML = `
        <div class="queue-item-info">
          <span class="file-ext-icon">${job.file_format}</span>
          <div>
            <div class="queue-item-name">${escapeHtml(job.original_filename)}</div>
            <div class="queue-item-meta">${sizeKb} KB | Pages: ${job.page_count} | Status: <strong style="color: ${statusColor}">${job.status.toUpperCase()}</strong></div>
          </div>
        </div>
        <div class="queue-item-actions">
          ${job.status === "ready" ? `<button class="btn btn-primary btn-sm btn-open-job" data-id="${job.job_id}">Open Document</button>` : ""}
          ${job.status === "failed" ? `<button class="btn btn-secondary btn-sm btn-retry-job" data-id="${job.job_id}">Retry</button>` : ""}
          ${job.status !== "ready" && job.status !== "failed" ? `<button class="btn btn-secondary btn-sm btn-track-job" data-id="${job.job_id}">View Progress</button>` : ""}
          <button class="btn btn-secondary btn-sm btn-del-job" data-id="${job.job_id}" title="Delete document">&times;</button>
        </div>
      `;
      queueList.appendChild(item);
    });

    // Attach click events
    queueList.querySelectorAll(".btn-open-job").forEach((btn) => {
      btn.addEventListener("click", () => openJobResult(btn.getAttribute("data-id")));
    });
    queueList.querySelectorAll(".btn-retry-job").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const jId = btn.getAttribute("data-id");
        showToast("Retrying document processing...", "info");
        try {
          const res = await fetch(`/api/jobs/${jId}/retry`, { method: "POST" });
          if (res.ok) {
            trackJob(jId);
          } else {
            showToast("Could not retry job.", "error");
          }
        } catch (e) {
          showToast("Network error retrying job.", "error");
        }
      });
    });
    queueList.querySelectorAll(".btn-track-job").forEach((btn) => {
      btn.addEventListener("click", () => trackJob(btn.getAttribute("data-id")));
    });
    queueList.querySelectorAll(".btn-del-job").forEach((btn) => {
      btn.addEventListener("click", () => deleteJob(btn.getAttribute("data-id")));
    });
  }

  btnClearQueue.addEventListener("click", async () => {
    const res = await fetch("/api/jobs");
    if (res.ok) {
      const jobs = await res.json();
      for (const j of jobs) {
        await fetch(`/api/jobs/${j.job_id}`, { method: "DELETE" });
      }
      loadQueue();
      showToast("Queue cleared.", "info");
    }
  });

  async function deleteJob(jobId) {
    if (!confirm("Are you sure you want to delete this document and all temporary processing data?")) return;
    try {
      const res = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
      if (res.ok) {
        showToast("Job deleted.", "info");
        if (state.currentJobId === jobId) {
          returnToUpload();
        }
        loadQueue();
      }
    } catch (e) {
      showToast("Error deleting job.", "error");
    }
  }

  const procErrorActions = document.getElementById("procErrorActions");
  const btnProcBack = document.getElementById("btnProcBack");
  const btnProcRetry = document.getElementById("btnProcRetry");

  if (btnProcBack) {
    btnProcBack.addEventListener("click", () => returnToUpload());
  }

  if (btnProcRetry) {
    btnProcRetry.addEventListener("click", async () => {
      if (!state.currentJobId) return;
      showToast("Retrying document processing...", "info");
      try {
        const res = await fetch(`/api/jobs/${state.currentJobId}/retry`, { method: "POST" });
        if (res.ok) {
          trackJob(state.currentJobId, procFileName.textContent);
        } else {
          showToast("Could not retry job.", "error");
        }
      } catch (e) {
        showToast("Network error retrying job.", "error");
      }
    });
  }

  // =========================================================================
  // PROCESSING SCREEN & POLLING
  // =========================================================================
  function trackJob(jobId, filename = "Document") {
    state.currentJobId = jobId;
    if (state.pollInterval) clearInterval(state.pollInterval);
    if (state.activeTimerInterval) clearInterval(state.activeTimerInterval);

    // Switch views
    uploadSection.style.display = "none";
    resultSection.style.display = "none";
    processingSection.style.display = "block";
    if (procErrorActions) procErrorActions.style.display = "none";

    procFileName.textContent = filename;
    procStageLabel.textContent = "Connecting to intelligence pipeline...";
    procStageLabel.style.color = "var(--text-muted)";
    progressBarFill.style.width = "5%";

    // Start timer
    state.processingStartTime = Date.now();
    state.activeTimerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - state.processingStartTime) / 1000);
      const mins = String(Math.floor(elapsed / 60)).padStart(2, "0");
      const secs = String(elapsed % 60).padStart(2, "0");
      procTimer.textContent = `${mins}:${secs}`;
    }, 1000);

    // Poll status
    state.pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}/status`);
        if (!res.ok) return;
        const status = await res.json();

        progressBarFill.style.width = `${status.progress_percent}%`;
        procStageLabel.textContent = status.stage_label || status.status;

        // Highlight pipeline step
        updatePipelineStep(status.status);

        if (status.status === "ready") {
          clearInterval(state.pollInterval);
          clearInterval(state.activeTimerInterval);
          if (procErrorActions) procErrorActions.style.display = "none";
          showToast("Document processing complete!", "success");
          openJobResult(jobId);
        } else if (status.status === "failed") {
          clearInterval(state.pollInterval);
          clearInterval(state.activeTimerInterval);
          showToast(`Processing failed: ${status.error_message}`, "error");
          procStageLabel.textContent = `Failed: ${status.error_message}`;
          procStageLabel.style.color = "var(--accent-red)";
          if (procErrorActions) procErrorActions.style.display = "flex";
        }
      } catch (err) {
        console.error("Poll error:", err);
      }
    }, 1000);
  }

  function updatePipelineStep(currentStatus) {
    const steps = ["validating", "preprocessing", "analysing", "extracting", "cleaning", "validating_result", "ready"];
    const currIdx = steps.indexOf(currentStatus);
    const nodes = pipelineSteps.querySelectorAll(".step-node");

    nodes.forEach((node, idx) => {
      node.classList.remove("active", "done");
      if (idx < currIdx) node.classList.add("done");
      else if (idx === currIdx) node.classList.add("active");
    });
  }

  // =========================================================================
  // RESULT WORKSPACE & VIEWER
  // =========================================================================
  async function openJobResult(jobId) {
    state.currentJobId = jobId;
    if (state.pollInterval) clearInterval(state.pollInterval);
    if (state.activeTimerInterval) clearInterval(state.activeTimerInterval);

    try {
      const res = await fetch(`/api/jobs/${jobId}/result`);
      if (!res.ok) {
        showToast("Could not load document result.", "error");
        return;
      }
      const masterDoc = await res.json();
      state.currentResult = masterDoc;
      state.currentPageNumber = 1;
      state.dirtyBlocks.clear();
      state.hasUnsavedChanges = false;
      btnSaveEdits.disabled = true;

      // Switch view
      uploadSection.style.display = "none";
      processingSection.style.display = "none";
      resultSection.style.display = "block";

      // Render Metadata
      docTitleInput.value = masterDoc.document_title || "Untitled Document";
      badgeDocType.textContent = (masterDoc.document_type || "general_notes").replace(/_/g, " ").toUpperCase();
      badgeDocLang.textContent = (masterDoc.languages && masterDoc.languages.length > 0)
        ? masterDoc.languages.map((l) => l.name).join(", ")
        : "English";

      const proc = masterDoc.processing || {};
      const modelName = proc.extraction_model || "Gemini 3.5 Flash-Lite";
      badgeModelUsed.textContent = proc.fallback_used ? `${modelName} (Fallback)` : modelName;

      // Uncertainties count
      let uncCount = 0;
      masterDoc.pages.forEach((p) => {
        p.blocks.forEach((b) => {
          uncCount += (b.uncertainties || []).length;
          if (b.review_status === "needs_review" || b.review_status === "unreadable") uncCount++;
        });
      });

      if (uncCount > 0) {
        badgeUncertainties.style.display = "inline-block";
        badgeUncertainties.textContent = `${uncCount} Uncertain`;
        uncertaintyBar.style.display = "flex";
        uncMessage.textContent = `${uncCount} uncertain handwriting section(s) detected. Highlighted below for your review.`;
      } else {
        badgeUncertainties.style.display = "none";
        uncertaintyBar.style.display = "none";
      }

      badgeEdited.style.display = masterDoc.user_edited ? "inline-block" : "none";

      // Render page preview on left
      renderSourcePage(1);

      // Render editor on right
      renderDocumentEditor();
      updateViewHelper();
    } catch (err) {
      showToast("Error rendering document: " + err.message, "error");
    }
  }

  function renderSourcePage(pageNum) {
    if (!state.currentResult || !state.currentResult.pages) return;
    state.currentPageNumber = pageNum;
    const totalPages = state.currentResult.pages.length;
    pageIndicator.textContent = `Page ${pageNum} of ${totalPages}`;

    btnPrevPage.disabled = pageNum <= 1;
    btnNextPage.disabled = pageNum >= totalPages;

    const pageData = state.currentResult.pages.find((p) => p.page_number === pageNum) || state.currentResult.pages[0];
    const previewFilename = pageData.preview_filename || `page_${pageNum}.jpg`;

    sourceImage.src = `/api/jobs/${state.currentJobId}/preview/${previewFilename}`;
    bboxOverlay.innerHTML = "";
  }

  btnPrevPage.addEventListener("click", () => {
    if (state.currentPageNumber > 1) renderSourcePage(state.currentPageNumber - 1);
  });
  btnNextPage.addEventListener("click", () => {
    if (state.currentResult && state.currentPageNumber < state.currentResult.pages.length) {
      renderSourcePage(state.currentPageNumber + 1);
    }
  });

  // Zoom controls
  btnZoomIn.addEventListener("click", () => {
    state.zoomScale = Math.min(state.zoomScale + 0.25, 3.0);
    applyZoom();
  });
  btnZoomOut.addEventListener("click", () => {
    state.zoomScale = Math.max(state.zoomScale - 0.25, 0.5);
    applyZoom();
  });
  btnZoomReset.addEventListener("click", () => {
    state.zoomScale = 1.0;
    applyZoom();
  });

  function applyZoom() {
    sourceCanvasWrapper.style.transform = `scale(${state.zoomScale})`;
    sourceCanvasWrapper.style.transformOrigin = "top center";
    zoomLevel.textContent = `${Math.round(state.zoomScale * 100)}%`;
  }

  function highlightBBox(bbox) {
    bboxOverlay.innerHTML = "";
    if (!bbox) return;

    const rect = document.createElement("div");
    rect.className = "bbox-highlight";
    rect.style.left = `${bbox.x * 100}%`;
    rect.style.top = `${bbox.y * 100}%`;
    rect.style.width = `${bbox.width * 100}%`;
    rect.style.height = `${bbox.height * 100}%`;
    bboxOverlay.appendChild(rect);

    // Scroll source viewport to highlight
    sourceImage.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // =========================================================================
  // DOCUMENT EDITOR (VERBATIM / CLEANED + STYLES)
  // =========================================================================
  function renderDocumentEditor() {
    if (!state.currentResult) return;
    documentCanvas.innerHTML = "";
    documentCanvas.className = `document-page-canvas mode-${state.currentStyle}`;

    const sortedPages = [...state.currentResult.pages].sort((a, b) => a.page_number - b.page_number);

    sortedPages.forEach((page, pIdx) => {
      if (sortedPages.length > 1) {
        const pageDivider = document.createElement("div");
        pageDivider.className = "page-canvas-divider";
        pageDivider.style.cssText = "font-size: 0.75rem; color: var(--text-muted); text-align: center; border-bottom: 1px dashed var(--border-color); margin: 24px 0 16px; padding-bottom: 4px;";
        pageDivider.textContent = `--- Page ${page.page_number} ---`;
        documentCanvas.appendChild(pageDivider);
      }

      const sortedBlocks = [...page.blocks].sort((a, b) => a.reading_order - b.reading_order);
      sortedBlocks.forEach((block) => {
        const blockEl = createBlockElement(block, page.page_number);
        documentCanvas.appendChild(blockEl);
      });
    });
  }

  function createBlockElement(block, pageNum) {
    const el = document.createElement("div");
    el.className = `doc-block ${block.uncertainties && block.uncertainties.length > 0 ? "has-uncertainty" : ""}`;
    el.setAttribute("data-block-id", block.id);
    el.setAttribute("data-page-num", pageNum);

    // Text source based on active tab
    const isCleaned = state.currentVersion === "cleaned";
    const text = isCleaned ? (block.cleaned_text || block.verbatim_text) : block.verbatim_text;

    // Focus & highlight click handler
    el.addEventListener("click", () => {
      documentCanvas.querySelectorAll(".doc-block").forEach((b) => b.classList.remove("focused"));
      el.classList.add("focused");

      if (state.currentPageNumber !== pageNum) {
        renderSourcePage(pageNum);
      }
      if (block.bbox) {
        highlightBBox(block.bbox);
      }
    });

    // 1. Heading or Title
    if (block.type === "title" || block.type === "heading") {
      const cls = block.type === "title" ? "block-title" : "block-heading";
      el.innerHTML = `<div class="${cls} editable-text" contenteditable="true" spellcheck="false">${escapeHtml(text)}</div>`;
    }
    // 2. Subheading
    else if (block.type === "subheading") {
      el.innerHTML = `<div class="block-subheading editable-text" contenteditable="true" spellcheck="false">${escapeHtml(text)}</div>`;
    }
    // 3. List
    else if (block.type === "list" && block.list_items && block.list_items.length > 0) {
      const listTag = block.list_items[0].list_type === "numbered" ? "ol" : "ul";
      let listHtml = `<${listTag} class="doc-list">`;
      block.list_items.forEach((item, liIdx) => {
        const liText = isCleaned && item.cleaned_text ? item.cleaned_text : item.verbatim_text;
        const prefix = item.list_type === "checkbox" ? `<input type="checkbox" ${item.is_checked ? "checked" : ""}> ` : "";
        listHtml += `<li class="editable-text" contenteditable="true" data-item-idx="${liIdx}">${prefix}${escapeHtml(liText)}</li>`;
      });
      listHtml += `</${listTag}>`;
      el.innerHTML = listHtml;
    }
    // 4. Table
    else if (block.type === "table" && block.table_data) {
      const td = block.table_data;
      const headers = (isCleaned && td.cleaned_headers) ? td.cleaned_headers : (td.headers || []);
      const rows = (isCleaned && td.cleaned_rows) ? td.cleaned_rows : (td.rows || []);

      let tableHtml = `<div class="table-wrapper"><table class="doc-table">`;
      if (headers.length > 0) {
        tableHtml += `<thead><tr>`;
        headers.forEach((h, hIdx) => {
          tableHtml += `<th class="table-cell-edit" contenteditable="true" data-h-idx="${hIdx}">${escapeHtml(h)}</th>`;
        });
        tableHtml += `</tr></thead>`;
      }
      tableHtml += `<tbody>`;
      rows.forEach((r, rIdx) => {
        tableHtml += `<tr>`;
        r.forEach((c, cIdx) => {
          tableHtml += `<td class="table-cell-edit" contenteditable="true" data-r-idx="${rIdx}" data-c-idx="${cIdx}">${escapeHtml(c)}</td>`;
        });
        tableHtml += `</tr>`;
      });
      tableHtml += `</tbody></table></div>`;
      el.innerHTML = tableHtml;
    }
    // 5. Key-Value
    else if (block.type === "key_value" && block.key_values && block.key_values.length > 0) {
      let kvHtml = `<div class="kv-grid">`;
      block.key_values.forEach((kv, kvIdx) => {
        const k = isCleaned && kv.cleaned_key ? kv.cleaned_key : kv.key;
        const v = isCleaned && kv.cleaned_value ? kv.cleaned_value : kv.value;
        kvHtml += `<div class="kv-key editable-text" contenteditable="true" data-kv-k="${kvIdx}">${escapeHtml(k)}:</div>`;
        kvHtml += `<div class="kv-val editable-text" contenteditable="true" data-kv-v="${kvIdx}">${escapeHtml(v)}</div>`;
      });
      kvHtml += `</div>`;
      el.innerHTML = kvHtml;
    }
    // 6. Equation
    else if (block.type === "equation") {
      el.innerHTML = `<div class="block-equation editable-text" contenteditable="true">${escapeHtml(text)}</div>`;
    }
    // 7. Standard Paragraph
    else {
      let contentHtml = escapeHtml(text);
      // Highlight uncertain words if verbatim mode
      if (!isCleaned && block.uncertainties && block.uncertainties.length > 0) {
        block.uncertainties.forEach((u) => {
          if (u.text && contentHtml.includes(u.text)) {
            contentHtml = contentHtml.replace(
              u.text,
              `<span class="uncertain-tag" title="Uncertain: ${escapeHtml(u.reason)}">${escapeHtml(u.text)}</span>`
            );
          }
        });
      }
      el.innerHTML = `<div class="block-paragraph editable-text" contenteditable="true" spellcheck="false">${contentHtml}</div>`;
    }

    // Attach input event to track edits
    const editables = el.querySelectorAll("[contenteditable=true]");
    editables.forEach((ed) => {
      ed.addEventListener("input", () => {
        markBlockDirty(block, el);
      });
    });

    return el;
  }

  function markBlockDirty(block, el) {
    state.hasUnsavedChanges = true;
    btnSaveEdits.disabled = false;
    badgeEdited.style.display = "inline-block";

    // Extract text from block element
    const fullText = el.innerText.trim();
    if (state.currentVersion === "cleaned") {
      block.cleaned_text = fullText;
      state.dirtyBlocks.set(block.id, {
        cleaned_text: fullText,
      });
    } else {
      block.verbatim_text = fullText;
      state.dirtyBlocks.set(block.id, {
        verbatim_text: fullText,
      });
    }
  }

  // Non-technical view explanation helper
  function updateViewHelper() {
    const helperEl = document.getElementById("viewHelperText");
    if (!helperEl) return;
    const isCleaned = state.currentVersion === "cleaned";
    const isProfessional = state.currentStyle === "professional";

    if (isCleaned && isProfessional) {
      helperEl.innerHTML = `<strong>Clean &amp; Polished (Standard Flow):</strong> Showing document with spelling corrected, clean headers, and neat tables in standard reading flow.`;
    } else if (!isCleaned && isProfessional) {
      helperEl.innerHTML = `<strong>Exact As Written (Standard Flow):</strong> Showing exact original words, spelling, shorthand, and punctuation as written on paper.`;
    } else if (isCleaned && !isProfessional) {
      helperEl.innerHTML = `<strong>Clean &amp; Polished (Match Paper Layout):</strong> Polished text arranged to reflect where blocks appeared on the original physical page.`;
    } else {
      helperEl.innerHTML = `<strong>Exact As Written (Match Paper Layout):</strong> Exact handwritten words arranged in their original spatial positions.`;
    }
  }

  // Version Switching (Clean & Polished vs Exact As Written)
  tabCleaned.addEventListener("click", () => {
    state.currentVersion = "cleaned";
    tabCleaned.classList.add("active");
    tabVerbatim.classList.remove("active");
    renderDocumentEditor();
    updateViewHelper();
  });

  tabVerbatim.addEventListener("click", () => {
    state.currentVersion = "verbatim";
    tabVerbatim.classList.add("active");
    tabCleaned.classList.remove("active");
    renderDocumentEditor();
    updateViewHelper();
  });

  // Presentation Style Switching (Standard Flow vs Match Paper Layout)
  btnStyleProfessional.addEventListener("click", () => {
    state.currentStyle = "professional";
    btnStyleProfessional.classList.add("active");
    btnStyleLayout.classList.remove("active");
    documentCanvas.className = "document-page-canvas mode-professional";
    updateViewHelper();
  });

  btnStyleLayout.addEventListener("click", () => {
    state.currentStyle = "layout";
    btnStyleLayout.classList.add("active");
    btnStyleProfessional.classList.remove("active");
    documentCanvas.className = "document-page-canvas mode-layout";
    updateViewHelper();
  });

  // Title edit
  docTitleInput.addEventListener("change", () => {
    if (state.currentResult) {
      state.currentResult.document_title = docTitleInput.value.trim();
      state.hasUnsavedChanges = true;
      btnSaveEdits.disabled = false;
    }
  });

  // Save Edits
  btnSaveEdits.addEventListener("click", async () => {
    if (!state.currentJobId) return;
    btnSaveEdits.disabled = true;

    try {
      for (const [bId, data] of state.dirtyBlocks.entries()) {
        await fetch(`/api/jobs/${state.currentJobId}/blocks/${bId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        });
      }

      state.dirtyBlocks.clear();
      state.hasUnsavedChanges = false;
      showToast("Changes saved successfully.", "success");
    } catch (e) {
      showToast("Failed to save changes: " + e.message, "error");
      btnSaveEdits.disabled = false;
    }
  });

  // Re-polish with My Edits (Regenerate Cleaned from edited text)
  btnRegenerateCleaned.addEventListener("click", async () => {
    if (!state.currentJobId) return;
    const confirmed = confirm(
      "Have the AI re-polish and re-format the document using your latest edits?\n\n" +
      "This will apply spelling and grammar polish while preserving your corrected words."
    );
    if (!confirmed) return;

    btnRegenerateCleaned.disabled = true;
    showToast("Re-polishing document with AI...", "info");

    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/clean`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Re-polishing failed.");
      const updatedDoc = await res.json();
      state.currentResult = updatedDoc;
      state.currentVersion = "cleaned";
      tabCleaned.classList.add("active");
      tabVerbatim.classList.remove("active");
      renderDocumentEditor();
      updateViewHelper();
      showToast("Document re-polished successfully!", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btnRegenerateCleaned.disabled = false;
    }
  });

  // Reset to Original AI Transcription
  btnRestoreOriginal.addEventListener("click", async () => {
    if (!state.currentJobId) return;
    const confirmed = confirm(
      "Reset back to the original AI transcription?\n\n" +
      "This will discard all your manual typing changes and restore the initial transcription."
    );
    if (!confirmed) return;

    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/restore`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Could not reset transcription.");
      const restored = await res.json();
      state.currentResult = restored;
      state.dirtyBlocks.clear();
      state.hasUnsavedChanges = false;
      btnSaveEdits.disabled = true;
      badgeEdited.style.display = "none";
      renderDocumentEditor();
      updateViewHelper();
      showToast("Reset back to original AI transcription.", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // =========================================================================
  // EXPORT & PRINT
  // =========================================================================
  btnExportMenu.addEventListener("click", (e) => {
    e.stopPropagation();
    exportDropdownMenu.parentElement.classList.toggle("open");
  });

  document.addEventListener("click", () => {
    exportDropdownMenu.parentElement.classList.remove("open");
  });

  exportDropdownMenu.querySelectorAll(".dropdown-item").forEach((item) => {
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      exportDropdownMenu.parentElement.classList.remove("open");
      const fmt = item.getAttribute("data-format");
      const ver = item.getAttribute("data-version") || state.currentVersion;
      const sty = item.getAttribute("data-style") || state.currentStyle;
      triggerExport(fmt, ver, sty);
    });
  });

  async function triggerExport(format, version, style) {
    if (!state.currentJobId) return;
    showToast(`Generating ${format.toUpperCase()} export (${version})...`, "info");

    try {
      const res = await fetch(`/api/jobs/${state.currentJobId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          format: format,
          version: version,
          style: style,
        }),
      });

      if (!res.ok) {
        showToast("Export failed.", "error");
        return;
      }

      // Extract filename from header
      const disp = res.headers.get("Content-Disposition");
      let filename = `nobeth_export.${format}`;
      if (disp && disp.includes("filename=")) {
        filename = disp.split("filename=")[1].replace(/"/g, "").trim();
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      showToast(`Exported ${filename}`, "success");
    } catch (err) {
      showToast("Export error: " + err.message, "error");
    }
  }

  btnPrint.addEventListener("click", () => {
    window.print();
  });

  // Navigation
  btnBackToUpload.addEventListener("click", () => {
    if (state.hasUnsavedChanges) {
      if (!confirm("You have unsaved edits. Return to queue without saving?")) return;
    }
    returnToUpload();
  });

  function returnToUpload() {
    resultSection.style.display = "none";
    processingSection.style.display = "none";
    uploadSection.style.display = "block";
    loadQueue();
  }

  // =========================================================================
  // MODALS & HELPERS
  // =========================================================================
  btnOpenSettings.addEventListener("click", () => (settingsModal.style.display = "flex"));
  btnCloseSettingsModal.addEventListener("click", () => (settingsModal.style.display = "none"));
  btnCloseSettingsBtn.addEventListener("click", () => (settingsModal.style.display = "none"));

  function escapeHtml(text) {
    if (!text) return "";
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initial load
  loadQueue();
});

