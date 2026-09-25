<template>
  <section class="page" data-module="knowledge">
    <header class="page-head">
      <div>
        <h2>运维知识库</h2>
        <p class="page-desc">案例取自缺陷登记与已验收消缺处理的既有记录，按设备类型与缺陷类型归档；值班时可按关键词检索往期案例，查看当时的处理措施与耗时。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出案例清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键词</span>
        <input v-model="filters.keyword" placeholder="缺陷编号 / 设备 / 缺陷类型 / 措施" />
      </label>
      <label class="filter-item">
        <span>设备类型</span>
        <select v-model="filters.device_type">
          <option value="">全部设备类型</option>
          <option v-for="item in deviceTypes" :key="item.name" :value="item.name">
            {{ item.name }}（{{ item.count }}）
          </option>
        </select>
      </label>
      <label class="filter-item">
        <span>缺陷类型</span>
        <select v-model="filters.defect_type">
          <option value="">全部缺陷类型</option>
          <option v-for="item in defectTypes" :key="item.name" :value="item.name">
            {{ item.name }}（{{ item.count }}）
          </option>
        </select>
      </label>
      <label class="filter-item">
        <span>完成时间起</span>
        <input v-model="filters.date_from" type="date" />
      </label>
      <label class="filter-item">
        <span>完成时间止</span>
        <input v-model="filters.date_to" type="date" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column" :class="{ 'cell-clamp': column === '处理措施' }">
            {{ row[column] ?? '—' }}
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 空态：某段时间没有沉淀案例时给引导，而不是留一片空白 -->
    <div v-if="!rows.length && !errorMessage" class="kb-empty">
      <strong>当前筛选条件下暂无沉淀案例</strong>
      <p>{{ hasActiveFilter ? '该时间段或关键词下还没有已验收的消缺案例，可放宽时间范围或清空关键词后再查。' : '已有消缺单完成验收后，处理措施会自动沉淀为案例，无需另行登记。' }}</p>
      <button v-if="hasActiveFilter" class="btn" type="button" @click="resetFilters">清空筛选条件</button>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条案例</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <article class="modal-card">
        <header class="modal-head">
          <div>
            <h3>{{ detail.案例编号 }} · {{ detail.缺陷类型 }}</h3>
            <p class="page-desc">案例描述取自缺陷登记记录，处理措施与耗时取自已验收消缺单。</p>
          </div>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>

        <div class="detail-tag-row">
          <span class="detail-tag">{{ detail.设备类型 }}</span>
          <span class="detail-tag">{{ detail.严重等级 }}</span>
          <span class="detail-tag">处理耗时 {{ detail.处理耗时 }}</span>
          <span v-if="detail.重复登记次数 > 0" class="detail-tag warn">
            同案例重复登记 {{ detail.重复登记次数 }} 次（{{ detail.重复消缺单号.join('、') }}），已合并展示
          </span>
        </div>

        <dl class="detail-grid">
          <template v-for="field in summaryFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </template>
        </dl>

        <section class="detail-block">
          <h4>当时的处理措施</h4>
          <p class="detail-measure">{{ detail.处理措施 }}</p>
        </section>

        <section v-if="detail.来源缺陷记录" class="detail-block">
          <h4>来源缺陷记录（缺陷登记，保证描述一致）</h4>
          <dl class="detail-grid compact">
            <template v-for="field in sourceDefectFields" :key="field">
              <dt>{{ field }}</dt>
              <dd>{{ detail.来源缺陷记录[field] ?? '—' }}</dd>
            </template>
          </dl>
        </section>

        <section v-if="detail.来源消缺记录?.length" class="detail-block">
          <h4>来源消缺记录（消缺处理，共 {{ detail.来源消缺记录.length }} 条，重复登记已去重）</h4>
          <ul class="source-list">
            <li v-for="repair in detail.来源消缺记录" :key="String(repair.消缺单号 ?? '')">
              <span class="source-no">{{ repair.消缺单号 }}</span>
              <span>{{ repair.处理人员 }} · {{ repair.完成时间 || '完成时间未填' }}</span>
              <span class="source-measure">{{ repair.处理措施 }}</span>
            </li>
          </ul>
        </section>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type CaseRow = Record<string, string | number | string[] | null>
type SourceRecord = Record<string, string | number | null>
type Detail = {
  id: number
  案例编号: string
  设备类型: string
  缺陷类型: string
  严重等级: string
  处理耗时: string
  重复登记次数: number
  重复消缺单号: string[]
  来源缺陷记录?: SourceRecord
  来源消缺记录?: SourceRecord[]
} & Record<string, string | number | string[] | null | SourceRecord | SourceRecord[]>
type FacetItem = { name: string; count: number }
type Meta = {
  total: number
  duplicated: number
  avg_duration: string
  latest_case_time: string | null
  device_types: FacetItem[]
  defect_types: FacetItem[]
}

const ENDPOINT = '/api/knowledge'
const columns = ['案例编号', '设备类型', '所属设备', '缺陷类型', '严重等级', '处理措施', '处理人员', '处理耗时', '完成时间']
const summaryFields = ['缺陷编号', '所属设备', '发现时间', '发现人', '处理期限', '消缺单号', '备件消耗', '验收人员']
const sourceDefectFields = ['缺陷编号', '所属设备', '缺陷类型', '严重等级', '发现时间', '发现人', '缺陷状态']

const rows = ref<CaseRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const detail = ref<Detail | null>(null)
const meta = ref<Meta | null>(null)

const filters = ref<Record<string, string>>({
  keyword: '',
  device_type: '',
  defect_type: '',
  date_from: '',
  date_to: '',
})

const deviceTypes = computed<FacetItem[]>(() => meta.value?.device_types ?? [])
const defectTypes = computed<FacetItem[]>(() => meta.value?.defect_types ?? [])
const hasActiveFilter = computed(() =>
  Object.values(filters.value).some((value) => value.trim() !== ''),
)
const stats = computed(() => [
  { label: '已沉淀案例', value: meta.value?.total ?? 0 },
  { label: '平均处理耗时', value: meta.value?.avg_duration ?? '—' },
  { label: '重复登记已合并', value: meta.value?.duplicated ?? 0 },
  { label: '最近沉淀日期', value: meta.value?.latest_case_time ?? '—' },
])

function resetFilters() {
  filters.value = { keyword: '', device_type: '', defect_type: '', date_from: '', date_to: '' }
  void reload()
}

function exportRows() {
  const query = buildQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value.trim()) {
      params.set(key, value.trim())
    }
  }
  return params.toString()
}

async function loadMeta() {
  try {
    const response = await request(`${ENDPOINT}/meta`)
    if (response.ok) {
      meta.value = await response.json()
    }
  } catch {
    // 统计卡不是主流程，加载失败时保持 0 值，不阻塞案例列表
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    if (!response.ok) {
      throw new Error('知识库案例读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '知识库案例读取失败'
  }
  void loadMeta()
}

async function openDetail(row: CaseRow) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('案例详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '案例详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

onMounted(reload)
</script>
