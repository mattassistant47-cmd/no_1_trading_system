import { useCallback } from 'react'

export const useApi = () => {
  const get = useCallback(async (endpoint) => {
    try {
      const response = await fetch(endpoint)

      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`)
      }

      const data = await response.json()
      return data
    } catch (error) {
      console.error('GET request failed:', error)
      throw error
    }
  }, [])

  const post = useCallback(async (endpoint, body) => {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`)
      }

      const data = await response.json()
      return data
    } catch (error) {
      console.error('POST request failed:', error)
      throw error
    }
  }, [])

  const put = useCallback(async (endpoint, body) => {
    try {
      const response = await fetch(endpoint, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`)
      }

      const data = await response.json()
      return data
    } catch (error) {
      console.error('PUT request failed:', error)
      throw error
    }
  }, [])

  const delete_ = useCallback(async (endpoint) => {
    try {
      const response = await fetch(endpoint, {
        method: 'DELETE',
      })

      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`)
      }

      const data = await response.json()
      return data
    } catch (error) {
      console.error('DELETE request failed:', error)
      throw error
    }
  }, [])

  return { get, post, put, delete: delete_ }
}
