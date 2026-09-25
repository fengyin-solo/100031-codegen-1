<template>
  <section class="page" data-module="knowledge">
    <header class="page-head">
      <div>
        <h2>运维知识库</h2>
        <p class="page-desc">案例来自已闭环的缺陷与已验收的消缺记录，按设备类型与缺陷类型归档；检索往期处理措施与耗时，辅助现场快速复处。</p>
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
        <input v-model="filters.keyword" placeholder="缺陷编号 / 设备 / 处理措施" />
      </label>
      <label class="filter-item">
        <span>设备类型</span>
        <select v-model="filters.device_type">
          <option value="">全部设备类型</option>
          <option v-for="item in deviceTypes" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>缺陷类型</span>
        <select v-model="filters.defect_type">
          <option value="">全部缺陷类型</option>
          <option v-for="item in defectTypes" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>沉淀时间起</span>
        <input v-model="filters.begin" type="date" />
      </label>
      <label class="filter-item">
        <span>沉淀时间止</span>
        <input v-model="filters.end" type="date" />
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看案例</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            {{ emptyHint }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条沉淀案例（同一缺陷仅沉淀一条，重复登记不重复展示）</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <article class="modal-card">
        <header class="modal-head">
          <h3>{{ detail['案例编号'] }} · {{ detail['设备类型'] }} / {{ detail['缺陷类型'] }}</h3>
          <button class="link" type="button" @click="detail = null">关闭</button>
        </header>
        <div class="modal-body">
          <section v-for="group in detailGroups" :key="group.title" class="detail-group">
            <h4>{{ group.title }}</h4>
            <dl class="detail-grid">
              <div
                v-for="field in group.fields"
                :key="field"
                class="detail-item"
                :class="{ wide: wideFields.includes(field) }"
              >
                <dt>{{ field }}</dt>
                <dd>{{ detail[field] ?? '—' }}</dd>
              </div>
            </dl>
          </section>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Detail = Record<string, string | number | null>

const ENDPOINT = '/api/knowledge'
const columns = ["案例编号", "设备类型", "缺陷类型", "缺陷编号", "所属设备", "处理措施", "处理人员", "处理耗时", "沉淀时间"]

const rows = ref<Row[]>([])
const total = ref(0)
const caseTotal = ref(0)
const errorMessage = ref('')
const detail = ref<Detail | null>(null)
const deviceTypes = ref<string[]>([])
const defectTypes = ref<string[]>([])
const filters = ref<Record<string, string>>({
  keyword: '',
  device_type: '',
  defect_type: '',
  begin: '',
  end: '',
})

const stats = computed(() => [
  { label: '已沉淀案例', value: caseTotal.value },
  { label: '设备类型', value: deviceTypes.value.length },
  { label: '缺陷类型', value: defectTypes.value.length },
  { label: '当前筛选结果', value: total.value },
])

// 某段时间没有案例时不能一片空白：区分「从未沉淀」与「当前筛选无结果」
const emptyHint = computed(() => {
  if (caseTotal.value === 0) {
    return '暂无沉淀案例：案例随缺陷闭环、消缺验收后自动生成，老的缺陷登记流程不变'
  }
  return '该时间段 / 条件下暂无沉淀案例，可放宽时间范围或清空筛选条件后重试'
})

const detailGroups = [
  { title: '缺陷信息（与缺陷登记一致）', fields: ["缺陷编号", "所属设备", "设备类型", "缺陷类型", "严重等级", "发现时间", "发现人", "处理期限", "缺陷状态"] },
  { title: '处理记录', fields: ["消缺单号", "处理措施", "备件消耗", "处理人员", "完成时间", "验收人员", "处理耗时", "沉淀时间"] },
]
// 长文本字段在详情栅格里占满整行，避免被挤压成竖排
const wideFields = ["处理措施", "备件消耗"]

function resetFilters() {
  filters.value = { keyword: '', device_type: '', defect_type: '', begin: '', end: '' }
  void reload()
}

function exportRows() {
  const params = new URLSearchParams()
  if (filters.value.keyword) params.set('keyword', filters.value.keyword)
  if (filters.value.device_type) params.set('device_type', filters.value.device_type)
  if (filters.value.defect_type) params.set('defect_type', filters.value.defect_type)
  window.open(`${ENDPOINT}/export/all?${params.toString()}`, '_blank')
}

async function openDetail(row: Row) {
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

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  Object.entries(filters.value).forEach(([key, value]) => {
    if (value) params.set(key, value)
  })
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('知识库案例读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 无筛选条件时的总量用于空状态文案判断
    if (!params.toString()) {
      caseTotal.value = total.value
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '知识库案例读取失败'
  }
}

async function loadFilters() {
  try {
    const response = await request(`${ENDPOINT}/filters`)
    if (response.ok) {
      const payload = await response.json()
      deviceTypes.value = payload['设备类型'] ?? []
      defectTypes.value = payload['缺陷类型'] ?? []
    }
  } catch {
    // 筛选项拉取失败不阻塞列表，下拉退化为空
  }
}

onMounted(async () => {
  await loadFilters()
  await reload()
})
</script>

<style scoped>
.filter-item select {
  min-width: 130px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: min(720px, 92vw);
  max-height: 84vh;
  overflow: auto;
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
}
.detail-group {
  margin-top: 12px;
}
.detail-group h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--muted);
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 16px;
  margin: 0;
}
.detail-item dt {
  font-size: 12px;
  color: var(--muted);
}
.detail-item dd {
  margin: 2px 0 0;
  font-size: 13px;
  word-break: break-all;
}
.detail-item.wide {
  grid-column: 1 / -1;
}
</style>
