import { defineStore } from 'pinia'
import { detectTimezone, detectLanguage } from '@/utils/timezone'
import i18n, { normalizeUiLanguage } from '@/i18n'

export const usePreferencesStore = defineStore('preferences', {
  state: () => ({
    language: detectLanguage(),
    timezone: detectTimezone(),
    detectedLanguage: detectLanguage(),
    detectedTimezone: detectTimezone(),
    isLoaded: false
  }),

  getters: {
    currentLanguage: (state) => state.language,
    currentTimezone: (state) => state.timezone,
    isAutoDetected: (state) => {
      return (
        state.language === state.detectedLanguage &&
        state.timezone === state.detectedTimezone
      )
    }
  },

  actions: {
    async setLanguage(language, saveToBackend = false) {
      // UI display language - only save to localStorage, not to backend Profile
      // Profile.language is for AI generation and backend logic, not UI display
      const normalizedLanguage = normalizeUiLanguage(language)
      this.language = normalizedLanguage
      i18n.global.locale.value = normalizedLanguage
      localStorage.setItem('userLanguage', normalizedLanguage)

      // Note: saveToBackend is kept for backward compatibility but should not be used
      // UI language switching should not affect Profile.language
      if (saveToBackend) {
        console.warn(
          'setLanguage with saveToBackend=true is deprecated. UI language should not sync to Profile.language'
        )
      }
    },

    setTimezone(timezone) {
      this.timezone = timezone
      localStorage.setItem('userTimezone', timezone)
    },

    loadFromLocalStorage() {
      const savedLanguage = localStorage.getItem('userLanguage')
      const savedTimezone = localStorage.getItem('userTimezone')

      if (savedLanguage) {
        const normalizedLanguage = normalizeUiLanguage(savedLanguage)
        this.language = normalizedLanguage
        i18n.global.locale.value = normalizedLanguage
        if (savedLanguage !== normalizedLanguage) {
          localStorage.setItem('userLanguage', normalizedLanguage)
        }
      }

      if (savedTimezone) {
        this.timezone = savedTimezone
      }

      this.isLoaded = true
    },

    loadFromBackend(preferences) {
      // This method is deprecated - language is now loaded from user.profile.language
      // Keep for backward compatibility with settings API
      if (preferences.language) {
        this.setLanguage(preferences.language, false) // Don't save to backend when loading from settings
      }

      if (preferences.scene) {
        // Store scene preference if needed
        localStorage.setItem('userScene', preferences.scene)
      }

      this.isLoaded = true
    },

    reset() {
      const normalizedLanguage = normalizeUiLanguage(this.detectedLanguage)
      this.language = normalizedLanguage
      this.timezone = this.detectedTimezone
      i18n.global.locale.value = normalizedLanguage
      localStorage.removeItem('userLanguage')
      localStorage.removeItem('userTimezone')
    }
  }
})
