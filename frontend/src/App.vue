<script setup>
import { ref } from 'vue'
import ImageGrid from './components/ImageGrid.vue'

const query = ref('')
const submittedQuery = ref('')
const page = ref(1)

const handleSearch = (e) => {
  e.preventDefault()
  const q = query.value.trim()
  if (!q) return
  submittedQuery.value = q
  page.value = 1
}
</script>

<template>
  <div style="text-align: center; padding: 30px; font-family: sans-serif">
    <form @submit="handleSearch" style="margin: 20px 0">
      <input
        v-model="query"
        type="text"
        placeholder="Введите запрос"
        style="
          padding: 10px 15px;
          width: 320px;
          font-size: 16px;
          border: 1px solid #ccc;
          border-radius: 4px;
        "
      />
      <button
        type="submit"
        style="
          margin-left: 10px;
          padding: 10px 20px;
          background: #007bff;
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
        "
      >
        Найти
      </button>
    </form>

  <ImageGrid :search-query="submittedQuery" :page="page" @update:page="page = $event" />
  </div>
</template>