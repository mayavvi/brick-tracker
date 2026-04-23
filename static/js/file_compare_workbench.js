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
    filteredProjects: [],
    filteredTasks: [],
    compoundSearch: '',
    compoundOpen: false,
    projectSearch: '',
    projectOpen: false,
    taskSearch: '',
    taskOpen: false,
    globalQcOpen: false,
    globalQcRows: [],
    globalQcLoading: false,

    standaloneCompareMode() {
      return !this.selectedProgram && this.resultMode === 'compare' && !!(this.compareP && this.compareQ);
    },

    matchesOptFilter(item, q) {
      const s = (q || '').trim().toLowerCase();
      if (!s) return true;
      return String(item).toLowerCase().includes(s);
    },

    compoundOptionItems() {
      const list = this.contexts.compounds || [];
      return list.filter((item) => this.matchesOptFilter(item, this.compoundSearch));
    },

    projectOptionItems() {
      const list = this.filteredProjects || [];
      return list.filter((item) => this.matchesOptFilter(item, this.projectSearch));
    },

    taskOptionItems() {
      const list = this.filteredTasks || [];
      return list.filter((item) => this.matchesOptFilter(item, this.taskSearch));
    },

    syncFilterSearchInputs() {
      this.compoundSearch = this.filters.compound || '';
      this.projectSearch = this.filters.project || '';
      this.taskSearch = this.filters.task || '';
    },

    async fetchFilterOptions(compound, project) {
      const p = new URLSearchParams();
      if (compound) p.set('compound', compound);
      if (project) p.set('project', project);
      return this.api('/api/files/filter-options?' + p.toString());
    },

    async refreshCascadeLists() {
      if (this.filters.compound) {
        const data = await this.fetchFilterOptions(
          this.filters.compound,
          this.filters.project || null,
        );
        this.filteredProjects = data.projects || [];
        this.filteredTasks = data.tasks || [];
        return;
      }
      this.filteredProjects = [...(this.contexts.projects || [])];
      this.filteredTasks = [...(this.contexts.tasks || [])];
    },

    async pickCompound(val) {
      this.filters.compound = val || '';
      this.compoundOpen = false;
      this.compoundSearch = val || '';
      this.filters.project = '';
      this.filters.task = '';
      this.projectSearch = '';
      this.taskSearch = '';
      await this.refreshCascadeLists();
      await this.loadPrograms();
    },

    async pickProject(val) {
      this.filters.project = val || '';
      this.projectOpen = false;
      this.projectSearch = val || '';
      this.filters.task = '';
      this.taskSearch = '';
      await this.refreshCascadeLists();
      await this.loadPrograms();
    },

    async pickTask(val) {
      this.filters.task = val || '';
      this.taskOpen = false;
      this.taskSearch = val || '';
      await this.loadPrograms();
    },

    async toggleGlobalQc() {
      this.globalQcOpen = !this.globalQcOpen;
      if (this.globalQcOpen) {
        await this.loadGlobalQcRows();
      }
    },

    async loadGlobalQcRows() {
      this.globalQcLoading = true;
      try {
        const params = new URLSearchParams();
        if (this.filters.compound) params.set('compound', this.filters.compound);
        if (this.filters.project) params.set('project', this.filters.project);
        if (this.filters.task) params.set('task', this.filters.task);
        this.globalQcRows = await this.api('/api/files/indexed-qc-timing?' + params.toString());
      } catch (err) {
        this.globalQcRows = [];
        this.toast(err.message || '加载 QC 检查失败', 'error');
      } finally {
        this.globalQcLoading = false;
      }
    },

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
      await this.refreshCascadeLists();
      this.syncFilterSearchInputs();
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

    // ── Web CLI ─────────────────────────────────────────────────
    cli: { open: false, cwd: [], history: [], historyIdx: -1, output: [], input: '' },

    toggleCli() {
      this.cli.open = !this.cli.open;
      if (this.cli.open) {
        queueMicrotask(() => {
          const inp = this.$refs.cliInput;
          if (inp) inp.focus();
        });
      }
    },

    cliPrompt() {
      const parts = this.cli.cwd;
      if (!parts || parts.length === 0) return 'peak:/$ ';
      return 'peak:/' + parts.join('/') + '$ ';
    },

    cliLineClass(type) {
      if (type === 'cmd')      return 'font-semibold' + ' ' + 'cli-color-prompt';
      if (type === 'error')    return 'cli-color-error';
      if (type === 'success')  return 'cli-color-success';
      if (type === 'header')   return 'font-semibold cli-color-header';
      if (type === 'diff-add') return 'cli-color-add';
      if (type === 'diff-del') return 'cli-color-del';
      if (type === 'diff-hunk') return 'font-semibold cli-color-hunk';
      return 'cli-color-muted';
    },

    cliPrint(text, type) {
      this.cli.output.push({ text: String(text), type: type || 'info' });
      queueMicrotask(() => {
        const el = this.$refs.cliOutput;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    cliPrintLines(lines, type) {
      for (const line of lines) {
        if (typeof line === 'string') this.cliPrint(line, type || 'info');
        else this.cliPrint(line.text, line.type || type || 'info');
      }
    },

    cliHistoryUp() {
      if (this.cli.history.length === 0) return;
      if (this.cli.historyIdx < 0) this.cli.historyIdx = this.cli.history.length;
      if (this.cli.historyIdx > 0) {
        this.cli.historyIdx--;
        this.cli.input = this.cli.history[this.cli.historyIdx];
      }
    },

    cliHistoryDown() {
      if (this.cli.historyIdx < 0) return;
      this.cli.historyIdx++;
      if (this.cli.historyIdx >= this.cli.history.length) {
        this.cli.historyIdx = -1;
        this.cli.input = '';
      } else {
        this.cli.input = this.cli.history[this.cli.historyIdx];
      }
    },

    _cliParseArgs(tokens) {
      const flags = {};
      const positional = [];
      let i = 0;
      while (i < tokens.length) {
        const t = tokens[i];
        if (t.startsWith('--')) {
          const key = t.slice(2);
          if (i + 1 < tokens.length && !tokens[i + 1].startsWith('-')) {
            flags[key] = tokens[i + 1];
            i += 2;
          } else {
            flags[key] = true;
            i++;
          }
        } else if (t.startsWith('-') && t.length === 2) {
          const key = t.slice(1);
          if (i + 1 < tokens.length && !tokens[i + 1].startsWith('-')) {
            flags[key] = tokens[i + 1];
            i += 2;
          } else {
            flags[key] = true;
            i++;
          }
        } else {
          positional.push(t);
          i++;
        }
      }
      return { flags, positional };
    },

    _cliCwdContext() {
      const cwd = this.cli.cwd || [];
      return {
        compound: cwd[0] || null,
        project: cwd[1] || null,
        task: cwd.slice(2).join('/') || null,
      };
    },

    _cliPad(str, len) {
      const s = String(str || '');
      return s.length >= len ? s : s + ' '.repeat(len - s.length);
    },

    async cliResolveProgram(name) {
      const ctx = this._cliCwdContext();
      if (!ctx.compound) {
        this.cliPrint('请先 cd 到某个 compound 下再操作程序', 'error');
        return null;
      }
      const params = new URLSearchParams();
      params.set('compound', ctx.compound);
      if (ctx.project) params.set('project', ctx.project);
      if (ctx.task) params.set('task', ctx.task);
      params.set('search', name);
      params.set('limit', '10');
      const rows = await this.api('/api/files/programs?' + params.toString());
      if (!rows || rows.length === 0) {
        this.cliPrint('未找到匹配程序: ' + name, 'error');
        return null;
      }
      const exact = rows.find(r => r.program_key.toUpperCase() === name.toUpperCase()
                                 || r.display_name.toUpperCase() === name.toUpperCase());
      if (exact) return exact;
      if (rows.length === 1) return rows[0];
      this.cliPrint('多个匹配, 请指定更精确的名称:', 'error');
      for (let i = 0; i < rows.length; i++) {
        this.cliPrint('  ' + (i + 1) + '. ' + rows[i].display_name + ' (' + rows[i].extension + ', ' + rows[i].version_count + ' versions)', 'info');
      }
      return null;
    },

    async cliResolveVersion(program, atN) {
      const ctx = this._cliCwdContext();
      const params = new URLSearchParams();
      params.set('program_key', program.program_key);
      if (program.extension) params.set('extension', program.extension);
      if (ctx.compound) params.set('compound', ctx.compound);
      if (ctx.project) params.set('project', ctx.project);
      if (ctx.task) params.set('task', ctx.task);
      const tl = await this.api('/api/files/timeline?' + params.toString());
      if (!tl || tl.length === 0) {
        this.cliPrint('该程序没有索引版本', 'error');
        return null;
      }
      const idx = (atN || 1) - 1;
      if (idx < 0 || idx >= tl.length) {
        this.cliPrint('@' + (idx + 1) + ' 超出范围 (共 ' + tl.length + ' 个版本)', 'error');
        return null;
      }
      return tl[idx];
    },

    _cliParseProgramToken(token) {
      const m = token.match(/^(.+?)@(\d+)$/);
      if (m) return { name: m[1], at: parseInt(m[2], 10) };
      return { name: token, at: 1 };
    },

    async cliRunLine(raw) {
      const line = (raw || '').trim();
      if (!line) return;
      this.cliPrint(this.cliPrompt() + line, 'cmd');
      this.cli.history.push(line);
      this.cli.historyIdx = -1;

      const parts = line.match(/"([^"]*)"|\S+/g) || [];
      const tokens = parts.map(t => t.replace(/^"|"$/g, ''));
      const cmd = (tokens[0] || '').toLowerCase();
      const rest = tokens.slice(1);

      const handlers = {
        help: () => this.cli_help(rest),
        cd: () => this.cli_cd(rest),
        pwd: () => this.cli_pwd(),
        ls: () => this.cli_ls(rest),
        cat: () => this.cli_cat(rest),
        timeline: () => this.cli_timeline(rest),
        diff: () => this.cli_diff(rest),
        qc: () => this.cli_qc(rest),
        snap: () => this.cli_snap(rest),
        status: () => this.cli_status(),
        reindex: () => this.cli_reindex(),
        clear: () => this.cli_clear(),
      };

      if (!handlers[cmd]) {
        this.cliPrint('未知命令: ' + cmd + ' (输入 help 查看帮助)', 'error');
        return;
      }
      try {
        await handlers[cmd]();
      } catch (err) {
        this.cliPrint('错误: ' + (err.message || String(err)), 'error');
      }
    },

    cli_help(args) {
      const cmds = {
        help:     'help [cmd]                  显示帮助',
        cd:       'cd <path>                   切换上下文 (cd QL1706, cd .., cd /)',
        pwd:      'pwd                         显示当前上下文路径',
        ls:       'ls [--ext .sas] [--role main|qc] [--search AE]  列出当前层级内容',
        cat:      'cat <program>[@n]           预览程序 (n=第几新版本, 默认1=最新)',
        timeline: 'timeline <program>          列出程序所有索引版本',
        diff:     'diff <P> <Q> [-w] [-i]      比较两个目标 (program[@n] 或 #file_id)',
        qc:       'qc                          当前上下文的 QC 检查表',
        snap:     'snap <program>[@n] [-n "note"]  为版本创建快照',
        status:   'status                      索引状态',
        reindex:  'reindex                     重建索引',
        clear:    'clear                       清屏',
      };
      if (args && args.length > 0) {
        const key = args[0].toLowerCase();
        if (cmds[key]) {
          this.cliPrint(cmds[key], 'info');
          if (key === 'cd') {
            this.cliPrintLines([
              '路径层级: / → compounds → projects → tasks',
              '示例:',
              '  cd QL1706                    进入 compound',
              '  cd QL1706/QL1706-307         进入 project',
              '  cd QL1706/QL1706-307/SP/dryrun  进入 task',
              '  cd ..                        上一级',
              '  cd /                         回到根目录',
            ]);
          }
          if (key === 'diff') {
            this.cliPrintLines([
              '每个目标可以是:',
              '  AE            程序名 (最新版本)',
              '  AE@2          程序名第2新版本',
              '  #123          索引文件 id',
              '标志:',
              '  -w            忽略空白',
              '  -i            忽略大小写',
            ]);
          }
        } else {
          this.cliPrint('未知命令: ' + key, 'error');
        }
        return;
      }
      this.cliPrint('可用命令:', 'header');
      for (const v of Object.values(cmds)) {
        this.cliPrint('  ' + v, 'info');
      }
      this.cliPrint('', 'info');
      this.cliPrint('路径层级: / → compound → project → task → programs', 'info');
      this.cliPrint('快捷键: Ctrl+` 打开/关闭, Esc 关闭, ↑↓ 历史', 'info');
    },

    async cli_cd(args) {
      if (!args || args.length === 0) {
        this.cli.cwd = [];
        this.cliPrint('/', 'info');
        return;
      }
      const target = args.join(' ');
      if (target === '/') {
        this.cli.cwd = [];
        this.cliPrint('/', 'info');
        return;
      }
      if (target === '..') {
        if (this.cli.cwd.length > 0) {
          const last = this.cli.cwd[this.cli.cwd.length - 1];
          if (last.includes('/')) {
            const parts = last.split('/');
            parts.pop();
            if (parts.length > 0) {
              this.cli.cwd = [...this.cli.cwd.slice(0, -1), parts.join('/')];
            } else {
              this.cli.cwd = this.cli.cwd.slice(0, -1);
            }
          } else {
            this.cli.cwd = this.cli.cwd.slice(0, -1);
          }
        }
        this.cliPrint(this.cli.cwd.length > 0 ? '/' + this.cli.cwd.join('/') : '/', 'info');
        return;
      }

      let segments;
      if (target.startsWith('/')) {
        segments = target.slice(1).split('/').filter(Boolean);
      } else {
        segments = [...this.cli.cwd];
        const tail = this.cli.cwd.length >= 3 ? this.cli.cwd[2] : null;
        const newParts = target.split('/').filter(Boolean);
        if (segments.length < 2) {
          segments = segments.concat(newParts);
        } else if (segments.length === 2) {
          segments = [segments[0], segments[1], newParts.join('/')];
        } else {
          segments = [segments[0], segments[1], (tail ? tail + '/' : '') + newParts.join('/')];
        }
      }

      if (segments.length === 0) {
        this.cli.cwd = [];
        this.cliPrint('/', 'info');
        return;
      }

      const compound = segments[0];
      if (!(this.contexts.compounds || []).includes(compound)) {
        const lc = compound.toLowerCase();
        const found = (this.contexts.compounds || []).find(c => c.toLowerCase() === lc);
        if (found) segments[0] = found;
        else {
          this.cliPrint('compound 不存在: ' + compound, 'error');
          return;
        }
      }

      if (segments.length >= 2) {
        const opts = await this.fetchFilterOptions(segments[0], null);
        const projects = opts.projects || [];
        if (!projects.includes(segments[1])) {
          const lc = segments[1].toLowerCase();
          const found = projects.find(p => p.toLowerCase() === lc);
          if (found) segments[1] = found;
          else {
            this.cliPrint('project 不存在: ' + segments[1] + ' (在 ' + segments[0] + ' 下)', 'error');
            return;
          }
        }
      }

      if (segments.length >= 3) {
        const opts = await this.fetchFilterOptions(segments[0], segments[1]);
        const tasks = opts.tasks || [];
        const taskPath = segments.slice(2).join('/');
        if (!tasks.includes(taskPath)) {
          const lc = taskPath.toLowerCase();
          const found = tasks.find(t => t.toLowerCase() === lc);
          if (found) {
            segments = [segments[0], segments[1], found];
          } else {
            const partial = tasks.filter(t => t.toLowerCase().startsWith(lc));
            if (partial.length === 1) {
              segments = [segments[0], segments[1], partial[0]];
            } else {
              this.cliPrint('task 不存在: ' + taskPath + ' (在 ' + segments[0] + '/' + segments[1] + ' 下)', 'error');
              if (partial.length > 1) {
                this.cliPrint('部分匹配:', 'info');
                for (const t of partial) this.cliPrint('  ' + t, 'info');
              }
              return;
            }
          }
        } else {
          segments = [segments[0], segments[1], taskPath];
        }
      }

      this.cli.cwd = segments.length > 3 ? [segments[0], segments[1], segments.slice(2).join('/')] : segments;
      this.cliPrint('/' + this.cli.cwd.join('/'), 'success');
    },

    cli_pwd() {
      this.cliPrint(this.cli.cwd.length > 0 ? '/' + this.cli.cwd.join('/') : '/', 'info');
    },

    async cli_ls(args) {
      const { flags } = this._cliParseArgs(args || []);
      const ctx = this._cliCwdContext();
      const depth = this.cli.cwd.length;

      if (depth === 0) {
        const compounds = this.contexts.compounds || [];
        if (compounds.length === 0) {
          this.cliPrint('(空 — 索引中没有 compounds)', 'info');
          return;
        }
        this.cliPrint(this._cliPad('COMPOUND', 24) + 'projects', 'header');
        this.cliPrint('-'.repeat(44), 'info');
        for (const c of compounds) {
          try {
            const opts = await this.fetchFilterOptions(c, null);
            this.cliPrint(this._cliPad(c, 24) + (opts.projects || []).length, 'info');
          } catch (_) {
            this.cliPrint(this._cliPad(c, 24) + '?', 'info');
          }
        }
        return;
      }

      if (depth === 1) {
        const opts = await this.fetchFilterOptions(ctx.compound, null);
        const projects = opts.projects || [];
        if (projects.length === 0) {
          this.cliPrint('(没有 projects)', 'info');
          return;
        }
        this.cliPrint(this._cliPad('PROJECT', 28) + 'tasks', 'header');
        this.cliPrint('-'.repeat(44), 'info');
        for (const p of projects) {
          try {
            const o2 = await this.fetchFilterOptions(ctx.compound, p);
            this.cliPrint(this._cliPad(p, 28) + (o2.tasks || []).length, 'info');
          } catch (_) {
            this.cliPrint(this._cliPad(p, 28) + '?', 'info');
          }
        }
        return;
      }

      if (depth === 2) {
        const opts = await this.fetchFilterOptions(ctx.compound, ctx.project);
        const tasks = opts.tasks || [];
        if (tasks.length === 0) {
          this.cliPrint('(没有 tasks)', 'info');
          return;
        }
        this.cliPrint('TASK', 'header');
        this.cliPrint('-'.repeat(36), 'info');
        for (const t of tasks) this.cliPrint('  ' + t, 'info');
        return;
      }

      const params = new URLSearchParams();
      params.set('compound', ctx.compound);
      if (ctx.project) params.set('project', ctx.project);
      if (ctx.task) params.set('task', ctx.task);
      if (flags.ext) params.set('extension', flags.ext);
      if (flags.role) params.set('role', flags.role);
      if (flags.search) params.set('search', flags.search);
      params.set('limit', '300');
      const rows = await this.api('/api/files/programs?' + params.toString());
      if (!rows || rows.length === 0) {
        this.cliPrint('(没有匹配的程序)', 'info');
        return;
      }
      this.cliPrint(
        this._cliPad('PROGRAM', 30) +
        this._cliPad('EXT', 8) +
        this._cliPad('VER', 6) +
        'LATEST',
        'header'
      );
      this.cliPrint('-'.repeat(70), 'info');
      for (const r of rows) {
        this.cliPrint(
          this._cliPad(r.display_name, 30) +
          this._cliPad(r.extension, 8) +
          this._cliPad(r.version_count, 6) +
          this.formatDateTime(r.latest_modified_time),
          'info'
        );
      }
    },

    async cli_cat(args) {
      if (!args || args.length === 0) {
        this.cliPrint('用法: cat <program>[@n]', 'error');
        return;
      }
      const parsed = this._cliParseProgramToken(args[0]);
      const program = await this.cliResolveProgram(parsed.name);
      if (!program) return;
      const version = await this.cliResolveVersion(program, parsed.at);
      if (!version) return;

      const prev = await this.api('/api/files/indexed-preview/' + version.id);
      this.cliPrint('--- ' + version.file_name + ' (id=' + version.id + ', ' + this.formatDateTime(version.modified_time) + ') ---', 'header');
      const lines = (prev.text || '').split('\n');
      const pad = String(lines.length).length;
      for (let i = 0; i < lines.length; i++) {
        this.cliPrint(String(i + 1).padStart(pad) + ' | ' + lines[i], 'info');
      }
      this.cliPrint('--- ' + prev.line_count + ' lines, ' + this.formatSize(prev.size_bytes) + ', ' + prev.encoding + ' ---', 'header');
    },

    async cli_timeline(args) {
      if (!args || args.length === 0) {
        this.cliPrint('用法: timeline <program>', 'error');
        return;
      }
      const program = await this.cliResolveProgram(args[0]);
      if (!program) return;

      const ctx = this._cliCwdContext();
      const params = new URLSearchParams();
      params.set('program_key', program.program_key);
      if (program.extension) params.set('extension', program.extension);
      if (ctx.compound) params.set('compound', ctx.compound);
      if (ctx.project) params.set('project', ctx.project);
      if (ctx.task) params.set('task', ctx.task);
      const tl = await this.api('/api/files/timeline?' + params.toString());

      if (!tl || tl.length === 0) {
        this.cliPrint('没有索引版本', 'info');
        return;
      }
      this.cliPrint(
        this._cliPad('@', 4) +
        this._cliPad('ID', 8) +
        this._cliPad('FILE', 28) +
        this._cliPad('PROJECT/TASK', 28) +
        'MTIME',
        'header'
      );
      this.cliPrint('-'.repeat(88), 'info');
      for (let i = 0; i < tl.length; i++) {
        const v = tl[i];
        this.cliPrint(
          this._cliPad('@' + (i + 1), 4) +
          this._cliPad(v.id, 8) +
          this._cliPad(v.file_name, 28) +
          this._cliPad(v.project + '/' + v.task, 28) +
          this.formatDateTime(v.modified_time),
          'info'
        );
      }
    },

    async cli_diff(args) {
      if (!args || args.length < 2) {
        this.cliPrint('用法: diff <P> <Q> [-w] [-i]', 'error');
        this.cliPrint('  P/Q: program[@n] 或 #file_id', 'info');
        return;
      }
      const { flags, positional } = this._cliParseArgs(args);
      if (positional.length < 2) {
        this.cliPrint('需要两个比较目标', 'error');
        return;
      }

      const resolveTarget = async (token) => {
        if (token.startsWith('#')) {
          const fid = parseInt(token.slice(1), 10);
          if (isNaN(fid)) { this.cliPrint('无效 file_id: ' + token, 'error'); return null; }
          return { file_id: fid };
        }
        const parsed = this._cliParseProgramToken(token);
        const program = await this.cliResolveProgram(parsed.name);
        if (!program) return null;
        const version = await this.cliResolveVersion(program, parsed.at);
        if (!version) return null;
        return { file_id: version.id };
      };

      const pTarget = await resolveTarget(positional[0]);
      if (!pTarget) return;
      const qTarget = await resolveTarget(positional[1]);
      if (!qTarget) return;

      const ignoreWs = flags.w === true || flags.w === 'true';
      const ignoreCi = flags.i === true || flags.i === 'true';

      const params = new URLSearchParams();
      params.set('a_file_id', String(pTarget.file_id));
      params.set('b_file_id', String(qTarget.file_id));
      if (ignoreWs) params.set('ignore_whitespace', 'true');
      if (ignoreCi) params.set('ignore_case', 'true');
      params.set('mode', 'unified');

      this.cliPrint('正在比较...', 'info');
      const data = await this.api('/api/files/indexed-diff?' + params.toString());
      const summ = data.summary || {};
      this.cliPrint(data.a_label + '  vs  ' + data.b_label, 'header');
      this.cliPrint('+' + (summ.inserted || 0) + ' / -' + (summ.deleted || 0) + ' / ~' + (summ.replaced || 0) + ' (' + (summ.total || 0) + ' lines)', 'info');

      for (const ul of (data.unified_lines || [])) {
        const k = ul.kind;
        if (k === 'hunk') {
          this.cliPrint(ul.text, 'diff-hunk');
        } else if (k === 'insert') {
          this.cliPrint('+' + (ul.text || ''), 'diff-add');
        } else if (k === 'delete') {
          this.cliPrint('-' + (ul.text || ''), 'diff-del');
        } else {
          this.cliPrint(' ' + (ul.text || ''), 'info');
        }
      }
    },

    async cli_qc(args) {
      const ctx = this._cliCwdContext();
      if (!ctx.compound) {
        this.cliPrint('请先 cd 到某个 compound 下再执行 qc', 'error');
        return;
      }
      const params = new URLSearchParams();
      params.set('compound', ctx.compound);
      if (ctx.project) params.set('project', ctx.project);
      if (ctx.task) params.set('task', ctx.task);

      const rows = await this.api('/api/files/indexed-qc-timing?' + params.toString());
      if (!rows || rows.length === 0) {
        this.cliPrint('(没有 QC 数据)', 'info');
        return;
      }
      this.cliPrint(
        this._cliPad('TASK', 22) +
        this._cliPad('PROGRAM', 20) +
        this._cliPad('MAIN LOG', 22) +
        this._cliPad('QC LOG', 22) +
        this._cliPad('STATUS', 14) +
        'STALE',
        'header'
      );
      this.cliPrint('-'.repeat(106), 'info');
      for (const r of rows) {
        const reason = r.reason || 'ok';
        const type = reason === 'qc-missing' ? 'error' : reason === 'qc-older' ? 'diff-del' : 'success';
        this.cliPrint(
          this._cliPad(r.task, 22) +
          this._cliPad(r.program, 20) +
          this._cliPad(this.formatDateTime(r.main_log_mtime), 22) +
          this._cliPad(this.formatDateTime(r.qc_log_mtime), 22) +
          this._cliPad(reason, 14) +
          String(r.stale),
          type
        );
      }
    },

    async cli_snap(args) {
      if (!args || args.length === 0) {
        this.cliPrint('用法: snap <program>[@n] [-n "note"]', 'error');
        return;
      }
      const { flags, positional } = this._cliParseArgs(args);
      if (positional.length === 0) {
        this.cliPrint('需要指定程序名', 'error');
        return;
      }
      const parsed = this._cliParseProgramToken(positional[0]);
      const program = await this.cliResolveProgram(parsed.name);
      if (!program) return;
      const version = await this.cliResolveVersion(program, parsed.at);
      if (!version) return;

      const prev = await this.api('/api/files/indexed-preview/' + version.id);
      const fullPath = prev.file && prev.file.full_path;
      if (!fullPath) {
        this.cliPrint('无法获取文件路径', 'error');
        return;
      }
      const note = flags.n || flags.note || '';
      const result = await this.api('/api/files/snapshot', {
        method: 'POST',
        body: JSON.stringify({ path: fullPath, note: note }),
      });
      const dedup = result.deduplicated ? ' (已去重, 内容未变)' : '';
      this.cliPrint('快照已创建: id=' + result.id + dedup, 'success');
    },

    async cli_status() {
      const s = await this.api('/api/files/status');
      this.cliPrint('索引文件数:   ' + s.indexed_files, 'info');
      this.cliPrint('程序组数:     ' + s.program_groups, 'info');
      this.cliPrint('最后索引时间: ' + this.formatDateTime(s.last_indexed_at), 'info');
    },

    async cli_reindex() {
      this.cliPrint('正在重建索引...', 'info');
      await this.api('/api/files/reindex', { method: 'POST' });
      await this.loadStatus();
      await this.loadContexts();
      this.cliPrint('索引重建完成', 'success');
      await this.cli_status();
    },

    cli_clear() {
      this.cli.output = [];
    },
  };
}
