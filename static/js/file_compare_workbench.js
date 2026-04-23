function codeIndexWorkbench() {
  return {
    status: { indexed_files: 0, program_groups: 0, last_indexed_at: null },
    contexts: { compounds: [], projects: [], tasks: [], extensions: [] },
    filters: { compound: '', project: '', task: '', extension: '', role: '' },
    searchQuery: '',
    programs: [],
    programLoading: false,
    reindexing: false,
    browserPanelOpen: true,
    selectedProgram: null,
    timeline: [],
    timelineLoading: false,
    selectedVersion: null,
    preview: null,
    _previewLineCache: null,
    previewRowHeight: 18,
    previewVisibleStart: 0,
    previewVisibleEnd: 0,
    snapshots: [],
    snapshotPanelOpen: true,
    resultMode: 'preview',
    compareP: null,
    compareQ: null,
    diffLoading: false,
    diffResult: null,
    diffViewMode: 'side-by-side',
    diffIgnoreWhitespace: false,
    diffIgnoreCase: false,
    diffRowHeight: 22,
    diffVisibleStart: 0,
    diffVisibleEnd: 0,
    diffUnifiedVisibleStart: 0,
    diffUnifiedVisibleEnd: 0,
    qcRows: [],
    qcLoading: false,

    async init() {
      await this.loadStatus();
      await this.loadContexts();
      await this.loadPrograms();
    },

    async api(url, options) {
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...(options || {}),
      });
      if (!response.ok) {
        let detail = response.statusText;
        try {
          const payload = await response.json();
          detail = payload.detail || detail;
        } catch (err) {}
        throw new Error(detail);
      }
      if (response.status === 204) return null;
      return response.json();
    },

    toast(message, type) {
      if (window.Alpine && Alpine.store('toast')) {
        Alpine.store('toast').push(message, type || 'info');
      }
    },

    async loadStatus() {
      this.status = await this.api('/api/files/status');
    },

    async loadContexts() {
      this.contexts = await this.api('/api/files/contexts');
    },

    buildProgramQuery() {
      const params = new URLSearchParams();
      if (this.searchQuery.trim()) params.set('search', this.searchQuery.trim());
      if (this.filters.compound) params.set('compound', this.filters.compound);
      if (this.filters.project) params.set('project', this.filters.project);
      if (this.filters.task) params.set('task', this.filters.task);
      if (this.filters.extension) params.set('extension', this.filters.extension);
      if (this.filters.role) params.set('role', this.filters.role);
      params.set('limit', '300');
      return params.toString();
    },

    async loadPrograms() {
      this.programLoading = true;
      try {
        this.programs = await this.api('/api/files/programs?' + this.buildProgramQuery());
        const stillSelected = this.selectedProgram && this.programs.find(
          (item) => item.display_name === this.selectedProgram.display_name
        );
        if (stillSelected) {
          this.selectedProgram = stillSelected;
        } else if (this.selectedProgram) {
          this.clearSelection();
        }
      } catch (err) {
        this.toast(err.message || '加载程序列表失败', 'error');
      } finally {
        this.programLoading = false;
      }
    },

    async rebuildIndex() {
      this.reindexing = true;
      try {
        await this.api('/api/files/reindex', { method: 'POST' });
        await this.loadStatus();
        await this.loadContexts();
        await this.loadPrograms();
        if (this.selectedProgram) {
          await this.selectProgram(this.selectedProgram, true);
        }
        this.toast('全局索引已重建', 'success');
      } catch (err) {
        this.toast(err.message || '重建索引失败', 'error');
      } finally {
        this.reindexing = false;
      }
    },

    toggleBrowserPanel() {
      this.browserPanelOpen = !this.browserPanelOpen;
    },

    clearSelection() {
      this.selectedProgram = null;
      this.timeline = [];
      this.selectedVersion = null;
      this.preview = null;
      this._previewLineCache = null;
      this.previewVisibleStart = 0;
      this.previewVisibleEnd = 0;
      this.snapshots = [];
      this.snapshotPanelOpen = true;
      this.resultMode = 'preview';
      this.compareP = null;
      this.compareQ = null;
      this.diffResult = null;
      this.diffVisibleStart = 0;
      this.diffVisibleEnd = 0;
      this.diffUnifiedVisibleStart = 0;
      this.diffUnifiedVisibleEnd = 0;
      this.qcRows = [];
    },

    programIsSelected(program) {
      return !!this.selectedProgram && this.selectedProgram.display_name === program.display_name;
    },

    async selectProgram(program, forceReload) {
      if (!forceReload && this.programIsSelected(program)) {
        this.clearSelection();
        return;
      }

      this.selectedProgram = program;
      this.timelineLoading = true;
      this.selectedVersion = null;
      this.preview = null;
      this._previewLineCache = null;
      this.snapshots = [];
      this.resultMode = 'preview';
      this.compareP = null;
      this.compareQ = null;
      this.diffResult = null;
      this.qcRows = [];

      try {
        const params = new URLSearchParams();
        params.set('program_key', program.program_key);
        if (program.extension) params.set('extension', program.extension);
        if (this.filters.compound) params.set('compound', this.filters.compound);
        if (this.filters.project) params.set('project', this.filters.project);
        if (this.filters.task) params.set('task', this.filters.task);
        if (this.filters.role) params.set('role', this.filters.role);
        this.timeline = await this.api('/api/files/timeline?' + params.toString());
        if (this.timeline.length > 0) {
          await this.selectVersion(this.timeline[0], false);
        }
      } catch (err) {
        this.toast(err.message || '加载版本历史失败', 'error');
      } finally {
        this.timelineLoading = false;
      }
    },

    async selectVersion(version, preserveMode) {
      this.selectedVersion = version;
      if (!preserveMode) {
        this.resultMode = 'preview';
      }
      await this.loadPreview(version.id);
    },

    async loadPreview(fileId) {
      try {
        this.preview = await this.api('/api/files/indexed-preview/' + fileId);
        this._previewLineCache = this.preview.text ? this.preview.text.split('\n') : [];
        this.previewVisibleStart = 0;
        this.previewVisibleEnd = 0;
        await this.loadSnapshots(this.preview.file.full_path);
        queueMicrotask(() => {
          const el = this.$refs.previewScrollContainer;
          if (el) {
            el.scrollTop = 0;
            this.onPreviewScroll({ target: el });
          }
        });
      } catch (err) {
        this.toast(err.message || '加载预览失败', 'error');
      }
    },

    onPreviewScroll(ev) {
      const el = ev.target;
      const st = el.scrollTop;
      const vh = el.clientHeight || 480;
      const rh = this.previewRowHeight;
      const total = this._previewLineCache ? this._previewLineCache.length : 0;
      const overscan = 20;
      this.previewVisibleStart = Math.max(0, Math.floor(st / rh) - overscan);
      const visible = Math.ceil(vh / rh) + overscan * 2 + 2;
      this.previewVisibleEnd = Math.min(total, this.previewVisibleStart + visible);
    },

    visiblePreviewRows() {
      if (!this._previewLineCache || this._previewLineCache.length === 0) return [];
      const end = this.previewVisibleEnd || this._previewLineCache.length;
      const out = [];
      for (let i = this.previewVisibleStart; i < end; i++) {
        out.push({ n: i + 1, text: this._previewLineCache[i] });
      }
      return out;
    },

    previewTopSpacer() {
      return this.previewVisibleStart * this.previewRowHeight;
    },

    previewBottomSpacer() {
      const total = this._previewLineCache ? this._previewLineCache.length : 0;
      if (total === 0) return 0;
      const end = this.previewVisibleEnd || total;
      const shown = end - this.previewVisibleStart;
      return Math.max(0, total - this.previewVisibleStart - shown) * this.previewRowHeight;
    },

    async loadSnapshots(path) {
      try {
        this.snapshots = await this.api('/api/files/snapshots?path=' + encodeURIComponent(path));
      } catch (err) {
        this.snapshots = [];
      }
    },

    async takeSnapshot() {
      if (!this.preview || !this.preview.file) return;
      try {
        await this.api('/api/files/snapshot', {
          method: 'POST',
          body: JSON.stringify({
            path: this.preview.file.full_path,
            note: this.selectedProgram ? this.selectedProgram.display_name : '',
          }),
        });
        await this.loadSnapshots(this.preview.file.full_path);
        this.toast('快照已创建', 'success');
      } catch (err) {
        this.toast(err.message || '创建快照失败', 'error');
      }
    },

    setCompareVersion(slot, version) {
      if (!version) return;
      const target = {
        type: 'file',
        file_id: version.id,
        label: version.file_name + ' | ' + version.project + '/' + version.task,
      };
      if (slot === 'p') this.compareP = target;
      else this.compareQ = target;
      this.resultMode = 'compare';
      if (this.compareP && this.compareQ) {
        this.runDiff();
      }
    },

    compareLabel(target) {
      return target ? target.label : '未设置';
    },

    swapCompareSides() {
      const hold = this.compareP;
      this.compareP = this.compareQ;
      this.compareQ = hold;
      if (this.diffResult) {
        this.runDiff();
      }
    },

    async compareLatestTwo() {
      if (this.timeline.length < 2) return;
      this.compareP = {
        type: 'file',
        file_id: this.timeline[0].id,
        label: this.timeline[0].file_name + ' | ' + this.timeline[0].project + '/' + this.timeline[0].task,
      };
      this.compareQ = {
        type: 'file',
        file_id: this.timeline[1].id,
        label: this.timeline[1].file_name + ' | ' + this.timeline[1].project + '/' + this.timeline[1].task,
      };
      this.resultMode = 'compare';
      await this.runDiff();
    },

    async compareSnapshotWithCurrent(snapshot) {
      if (!snapshot || !this.selectedVersion) return;
      this.compareP = {
        type: 'snapshot',
        snap_id: snapshot.id,
        label: 'Snapshot #' + snapshot.id,
      };
      this.compareQ = {
        type: 'file',
        file_id: this.selectedVersion.id,
        label: this.selectedVersion.file_name + ' | 当前版本',
      };
      this.resultMode = 'compare';
      await this.runDiff();
    },

    async compareQcRow(row) {
      if (!row || !row.main_sas_path || !row.qc_sas_path) return;
      this.compareP = {
        type: 'path',
        path: row.main_sas_path,
        label: row.program + ' | main',
      };
      this.compareQ = {
        type: 'path',
        path: row.qc_sas_path,
        label: row.program + ' | qc',
      };
      this.resultMode = 'compare';
      await this.runDiff();
    },

    buildDiffParams() {
      const params = new URLSearchParams();
      this.appendCompareTarget(params, 'a', this.compareP);
      this.appendCompareTarget(params, 'b', this.compareQ);
      if (this.diffIgnoreWhitespace) params.set('ignore_whitespace', 'true');
      if (this.diffIgnoreCase) params.set('ignore_case', 'true');
      params.set('mode', 'unified');
      return params.toString();
    },

    appendCompareTarget(params, prefix, target) {
      if (!target) return;
      if (target.type === 'file') params.set(prefix + '_file_id', String(target.file_id));
      if (target.type === 'snapshot') params.set(prefix + '_snap_id', String(target.snap_id));
      if (target.type === 'path') params.set(prefix + '_path', target.path);
    },

    async runDiff() {
      if (!this.compareP || !this.compareQ) return;
      this.diffLoading = true;
      this.resultMode = 'compare';
      try {
        this.diffResult = await this.api('/api/files/indexed-diff?' + this.buildDiffParams());
        this.diffVisibleStart = 0;
        this.diffVisibleEnd = 0;
        this.diffUnifiedVisibleStart = 0;
        this.diffUnifiedVisibleEnd = 0;
        queueMicrotask(() => {
          const side = this.$refs.diffSideScrollContainer;
          if (side) {
            side.scrollTop = 0;
            this.onDiffSideScroll({ target: side });
          }
          const uni = this.$refs.diffUnifiedScrollContainer;
          if (uni) {
            uni.scrollTop = 0;
            this.onDiffUnifiedScroll({ target: uni });
          }
        });
      } catch (err) {
        this.toast(err.message || '读取比较结果失败', 'error');
      } finally {
        this.diffLoading = false;
      }
    },

    async rerunDiff() {
      if (!this.diffResult) return;
      await this.runDiff();
    },

    setDiffViewMode(mode) {
      this.diffViewMode = mode === 'unified' ? 'unified' : 'side-by-side';
      queueMicrotask(() => {
        const side = this.$refs.diffSideScrollContainer;
        if (side && this.diffViewMode === 'side-by-side') {
          this.onDiffSideScroll({ target: side });
        }
        const uni = this.$refs.diffUnifiedScrollContainer;
        if (uni && this.diffViewMode === 'unified') {
          this.onDiffUnifiedScroll({ target: uni });
        }
      });
    },

    onDiffSideScroll(ev) {
      const el = ev.target;
      const lines = (this.diffResult && this.diffResult.lines) || [];
      const st = el.scrollTop;
      const vh = el.clientHeight || 400;
      const rh = this.diffRowHeight;
      const total = lines.length;
      const overscan = 15;
      this.diffVisibleStart = Math.max(0, Math.floor(st / rh) - overscan);
      const visible = Math.ceil(vh / rh) + overscan * 2 + 2;
      this.diffVisibleEnd = Math.min(total, this.diffVisibleStart + visible);
    },

    visibleDiffLines() {
      const lines = (this.diffResult && this.diffResult.lines) || [];
      if (!lines.length) return [];
      const end = this.diffVisibleEnd || lines.length;
      const out = [];
      for (let i = this.diffVisibleStart; i < end; i++) {
        out.push({ idx: i, line: lines[i] });
      }
      return out;
    },

    diffTopSpacer() {
      return this.diffVisibleStart * this.diffRowHeight;
    },

    diffBottomSpacer() {
      const lines = (this.diffResult && this.diffResult.lines) || [];
      const total = lines.length;
      if (total === 0) return 0;
      const end = this.diffVisibleEnd || total;
      const shown = end - this.diffVisibleStart;
      return Math.max(0, total - this.diffVisibleStart - shown) * this.diffRowHeight;
    },

    onDiffUnifiedScroll(ev) {
      const el = ev.target;
      const lines = (this.diffResult && this.diffResult.unified_lines) || [];
      const st = el.scrollTop;
      const vh = el.clientHeight || 400;
      const rh = this.diffRowHeight;
      const total = lines.length;
      const overscan = 15;
      this.diffUnifiedVisibleStart = Math.max(0, Math.floor(st / rh) - overscan);
      const visible = Math.ceil(vh / rh) + overscan * 2 + 2;
      this.diffUnifiedVisibleEnd = Math.min(total, this.diffUnifiedVisibleStart + visible);
    },

    visibleUnifiedLines() {
      const lines = (this.diffResult && this.diffResult.unified_lines) || [];
      if (!lines.length) return [];
      const end = this.diffUnifiedVisibleEnd || lines.length;
      const out = [];
      for (let i = this.diffUnifiedVisibleStart; i < end; i++) {
        out.push({ idx: i, line: lines[i] });
      }
      return out;
    },

    diffUnifiedTopSpacer() {
      return this.diffUnifiedVisibleStart * this.diffRowHeight;
    },

    diffUnifiedBottomSpacer() {
      const lines = (this.diffResult && this.diffResult.unified_lines) || [];
      const total = lines.length;
      if (total === 0) return 0;
      const end = this.diffUnifiedVisibleEnd || total;
      const shown = end - this.diffUnifiedVisibleStart;
      return Math.max(0, total - this.diffUnifiedVisibleStart - shown) * this.diffRowHeight;
    },

    async setResultMode(mode) {
      this.resultMode = mode;
      if (mode === 'qc') {
        await this.loadQcRows();
      }
      if (mode === 'compare' && this.compareP && this.compareQ && !this.diffResult) {
        await this.runDiff();
      }
    },

    async loadQcRows() {
      this.qcLoading = true;
      try {
        const params = new URLSearchParams();
        const project = this.filters.project || (this.selectedVersion && this.selectedVersion.project) || '';
        const task = this.filters.task || (this.selectedVersion && this.selectedVersion.task) || '';
        const compound = this.filters.compound || (this.selectedVersion && this.selectedVersion.compound) || '';
        if (compound) params.set('compound', compound);
        if (project) params.set('project', project);
        if (task) params.set('task', task);
        this.qcRows = await this.api('/api/files/indexed-qc-timing?' + params.toString());
      } catch (err) {
        this.qcRows = [];
        this.toast(err.message || '加载 QC 检查失败', 'error');
      } finally {
        this.qcLoading = false;
      }
    },

    diffSummary() {
      if (!this.diffResult || !this.diffResult.summary) return '';
      const summary = this.diffResult.summary;
      return '+' + summary.inserted + ' / -' + summary.deleted + ' / ~' + summary.replaced + ' (' + summary.total + ' 行)';
    },

    diffCellClass(op, side) {
      if (op === 'insert' && side === 'q') return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
      if (op === 'delete' && side === 'p') return 'bg-rose-500/10 text-rose-700 dark:text-rose-300';
      if (op === 'replace') {
        return side === 'p'
          ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
          : 'bg-sky-500/10 text-sky-700 dark:text-sky-300';
      }
      return 'text-stone-800 dark:text-stone-200';
    },

    unifiedLineClass(line) {
      if (!line) return 'text-stone-800 dark:text-stone-200';
      if (line.kind === 'hunk') return 'text-neon-600 dark:text-neon-300 font-semibold';
      if (line.kind === 'insert') return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
      if (line.kind === 'delete') return 'bg-rose-500/10 text-rose-700 dark:text-rose-300';
      return 'text-stone-800 dark:text-stone-200';
    },

    joinCompact(items) {
      return (items || []).join(' · ');
    },

    formatDateTime(value) {
      if (!value) return '—';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.getFullYear() + '-' +
        String(date.getMonth() + 1).padStart(2, '0') + '-' +
        String(date.getDate()).padStart(2, '0') + ' ' +
        String(date.getHours()).padStart(2, '0') + ':' +
        String(date.getMinutes()).padStart(2, '0');
    },

    formatSize(bytes) {
      const num = Number(bytes || 0);
      if (num < 1024) return num + ' B';
      if (num < 1024 * 1024) return (num / 1024).toFixed(1) + ' KB';
      return (num / (1024 * 1024)).toFixed(1) + ' MB';
    },

    qcText(reason) {
      if (reason === 'qc-older') return 'QC 落后';
      if (reason === 'qc-missing') return '缺少 QC';
      return '正常';
    },

    qcBadgeClass(reason) {
      if (reason === 'qc-older') return 'bg-amber-500/15 text-amber-700 dark:text-amber-300';
      if (reason === 'qc-missing') return 'bg-rose-500/15 text-rose-700 dark:text-rose-300';
      return 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300';
    },
  };
}
