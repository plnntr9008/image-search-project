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
const perPage = 50
// When user deletes images we will fetch additional items from following pages
let nextFetchPage = props.page + 1
// track indexes currently animating removal
const removingIndexes = ref(new Set())

const fetchImages = async () => {
  if (!props.searchQuery) {
    images.value = []
    return
  }

  loading.value = true
  error.value = null

  try {
  // Используем относительный URL — nginx будет проксировать /search на бэкенд
  // perPage переменная задаёт количество элементов на страницу
  const url = `/search?query=${encodeURIComponent(props.searchQuery)}&page=${props.page}&per_page=${perPage}`
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
    // reset nextFetchPage when we load a new page
    nextFetchPage = props.page + 1
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

// Remove image from current grid (double-click handler). After removal
// we try to fetch the next available image from subsequent pages to
// keep the grid full. This simulates shifting images on following pages.
const removeImageAt = async (index) => {
  if (index < 0 || index >= images.value.length) return
  // animate removal: mark index as removing so CSS can transition
  removingIndexes.value.add(index)
  // wait for animation to play (250ms)
  await new Promise((r) => setTimeout(r, 260))

  // replace with a placeholder entry that shows a spinner
  images.value.splice(index, 1, { __placeholder: true })
  if (total.value > 0) total.value -= 1

  // attempt to fetch one image from the next page (per_page=1)
  try {
    const fetchPage = nextFetchPage
    const url = `/search?query=${encodeURIComponent(props.searchQuery)}&page=${fetchPage}&per_page=1`
    const res = await fetch(url)
    if (res.ok) {
      const data = await res.json()
      const item = (data.results && data.results[0]) || null
      if (item) {
        // replace placeholder with fetched item
        images.value.splice(index, 1, item)
        nextFetchPage = fetchPage + 1
      } else {
        // no replacement available — remove placeholder
        images.value.splice(index, 1)
      }
    } else {
      // on http error remove placeholder
      images.value.splice(index, 1)
    }
  } catch (e) {
    console.error('failed to fetch replacement image', e)
    images.value.splice(index, 1)
  } finally {
    // clear removing flag (if still present)
    removingIndexes.value.delete(index)
  }
}

const downloadZip = async () => {
  if (images.value.length === 0) return
  //loading.value = true
  error.value = null
  try {
  const zip = new JSZip()
  const folderName = `images_${props.searchQuery.replace(/\s+/g, '_')}_page${props.page}`
  const concurrency = 6
  const size = 50

    const loadImage = (url) => new Promise((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => resolve(img)
      img.onerror = (e) => reject(e)
      img.src = url
    })

    const canvasToBlob = (canvas) => new Promise((resolve) => {
      canvas.toBlob((b) => resolve(b), 'image/jpeg', 0.85)
    })

    for (let i = 0; i < images.value.length; i += concurrency) {
      const batch = images.value.slice(i, i + concurrency).map(async (img, idx) => {
        const index = i + idx
        try {
          const imageEl = await loadImage(img.download_url)
          // create canvas and draw center-cropped square
          const canvas = document.createElement('canvas')
          canvas.width = size
          canvas.height = size
          const ctx = canvas.getContext('2d')

          const iw = imageEl.naturalWidth
          const ih = imageEl.naturalHeight
          const side = Math.min(iw, ih)
          const sx = Math.floor((iw - side) / 2)
          const sy = Math.floor((ih - side) / 2)

          // draw cropping
          ctx.drawImage(imageEl, sx, sy, side, side, 0, 0, size, size)

          const blob = await canvasToBlob(canvas)
          return { index, blob, mime: blob.type }
        } catch (e) {
          console.error('image load/process failed', e)
          return { index, blob: null }
        }
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
    //loading.value = false
  }
}
</script>

<template>
  <div>
    <div v-if="error" style="color: red; margin: 20px;">{{ error }}</div>

    <div v-else-if="loading">Загрузка изображений...</div>

    <div v-else-if="images.length === 0 && searchQuery">
      Ничего не найдено.
    </div>

    <div v-else-if="images.length > 0">
        <div style="display: grid; grid-template-columns: repeat(auto-fill, 100px); gap: 8px; justify-content: center">
          <div
            v-for="(img, idx) in images"
            :key="img.id || img.download_url || idx"
            :class="{ removing: (removingIndexes && removingIndexes.value && removingIndexes.value.has && removingIndexes.value.has(idx)) }"
            style="width: 100px; height: 100px; overflow: hidden; border: 1px solid #eee; cursor: pointer; display:flex;align-items:center;justify-content:center;position:relative"
          >
            <template v-if="img && img.__placeholder">
              <div class="spinner" aria-hidden="true"></div>
            </template>

            <template v-else>
              <img
                v-if="img"
                :src="img.download_url"
                :alt="img.alt_description || 'preview'"
                style="width: 100%; height: 100%; object-fit: cover"
                @dblclick="() => removeImageAt(idx)"
              />
              <div v-else class="spinner" aria-hidden="true"></div>
            </template>
          </div>
        </div>

      <div style="margin-top: 20px">
        <button @click="prevPage" :disabled="page <= 1" style="margin: 0 5px">← Назад</button>
        <span>Стр. {{ page }} из макс. 10</span>
        <button @click="nextPage" :disabled="images.length < perPage" style="margin: 0 5px">Вперёд →</button>
      </div>


        <button
          @click="downloadZip"
          :disabled="images.length === 0 || loading"
          style="
            margin-top: 20px;
            padding: 8px 16px;
            background: #28a745;
            color: white;
            border: none;
            border-radius: 4px;
            margin-bottom: 15px;
            cursor: pointer;
          "
        >
        Скачать картинки в ZIP
      </button>

    </div>
  </div>
</template>

<style scoped>
.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(0,0,0,0.1);
  border-top: 3px solid rgba(0,0,0,0.6);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.removing {
  transition: transform 220ms ease, opacity 220ms ease;
  transform-origin: center;
  opacity: 0.01;
  transform: scale(0.85);
}
</style>