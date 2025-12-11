<script setup>
import { ref, watch } from 'vue'
import JSZip from 'jszip'

const props = defineProps({
  searchQuery: { type: String, required: true },
  page: { type: Number, required: true }
})

const emit = defineEmits(['update:page'])

const images = ref([])
const loading = ref(false)
const error = ref(null)
const total = ref(0)

const fetchImages = async () => {
  if (!props.searchQuery) {
    images.value = []
    return
  }

  loading.value = true
  error.value = null

  try {
    // URL-кодирование делает fetch автоматически, но явно используем encodeURIComponent для надёжности
    const url = `http://localhost:8000/search?query=${encodeURIComponent(props.searchQuery)}&page=${props.page}&per_page=50`
    const res = await fetch(url)

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }

    const data = await res.json()

    if (data.error) {
      throw new Error(data.error)
    }

    images.value = data.results || []
    total.value = data.total || 0
  } catch (err) {
    console.error(err)
    error.value = err.message || 'Ошибка загрузки'
    images.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.searchQuery, props.page],
  () => fetchImages(),
  { immediate: true }
)

const nextPage = () => {
  if (props.page < 10) emit('update:page', props.page + 1)
}
const prevPage = () => {
  if (props.page > 1) emit('update:page', props.page - 1)
}

const downloadZip = async () => {
  if (images.value.length === 0) return
  loading.value = true
  error.value = null
  try {
    const zip = new JSZip()
    const folderName = `images_${props.searchQuery.replace(/\s+/g, '_')}_page${props.page}`
    const concurrency = 6

    const fetchBlob = async (url) => {
      const res = await fetch(url, { mode: 'cors' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return await res.blob()
    }

    // fetch in batches to avoid too many parallel requests
    for (let i = 0; i < images.value.length; i += concurrency) {
      const batch = images.value.slice(i, i + concurrency).map((img, idx) => {
        const index = i + idx
        return fetchBlob(img.download_url)
          .then((blob) => ({ index, blob, mime: blob.type }))
          .catch(() => ({ index, blob: null }))
      })

      const batchResults = await Promise.all(batch)
      batchResults.forEach((r) => {
        if (r.blob) {
          const ext = (r.mime && r.mime.split('/')[1]) || 'jpg'
          zip.file(`${folderName}/image_${props.page}_${r.index + 1}.${ext}`, r.blob)
        }
      })
    }

    const content = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
    const objectUrl = URL.createObjectURL(content)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = `${folderName}.zip`
    document.body.appendChild(a)
    a.click()
    URL.revokeObjectURL(objectUrl)
    document.body.removeChild(a)
  } catch (err) {
    console.error(err)
    error.value = err.message || 'Ошибка создания ZIP'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <div v-if="error" style="color: red; margin: 20px;">{{ error }}</div>

    <div v-else-if="loading">Загрузка изображений...</div>

    <div v-else-if="images.length === 0 && searchQuery">
      Ничего не найдено. Попробуйте английский запрос (например: "cat", "bicycle").
    </div>

    <div v-else-if="images.length > 0">
      <p>Найдено: {{ total }} изображений (показаны квадратные 300×300)</p>
      <button
        @click="downloadZip"
        :disabled="images.length === 0 || loading"
        style="
          padding: 8px 16px;
          background: #28a745;
          color: white;
          border: none;
          border-radius: 4px;
          margin-bottom: 15px;
          cursor: pointer;
        "
      >
        Скачать страницу в ZIP ({{ images.length }})
      </button>

      <div style="display: grid; grid-template-columns: repeat(auto-fill, 300px); gap: 12px; justify-content: center">
        <div
          v-for="img in images"
          :key="img.id"
          style="width: 300px; height: 300px; overflow: hidden; border: 1px solid #eee"
        >
          <img
            :src="img.download_url"
            :alt="img.alt_description || 'preview'"
            style="width: 100%; height: 100%; object-fit: cover"
          />
        </div>
      </div>

      <div style="margin-top: 20px">
        <button @click="prevPage" :disabled="page <= 1" style="margin: 0 5px">← Назад</button>
        <span>Стр. {{ page }} из макс. 10</span>
        <button @click="nextPage" :disabled="images.length < 50" style="margin: 0 5px">Вперёд →</button>
      </div>
    </div>
  </div>
</template>