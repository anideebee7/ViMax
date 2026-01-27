# 🔑 API Keys Setup Guide

This guide explains how to obtain the three API keys required to use ViMax.

## Required API Keys

ViMax requires **3 API keys** for full functionality:

1. **OpenRouter API Key** - For chat model (script planning, storyboarding, etc.)
2. **Google AI Studio API Key** - For image generation (Nanobanana/Gemini Image API)
3. **Google AI Studio API Key** - For video generation (Veo Video API)

---

## 1. OpenRouter API Key (Chat Model)

### What it's used for:
- Script planning and enhancement
- Storyboard generation
- Character and scene extraction
- All text-based AI operations

### How to get it:

1. **Visit OpenRouter**
   - Go to [https://openrouter.ai/](https://openrouter.ai/)
   - Click "Sign In" or "Sign Up"

2. **Create an API Key**
   - After logging in, navigate to [API Keys](https://openrouter.ai/keys)
   - Click the **"Create Key"** button
   - Give your key a name (e.g., "ViMax Chat Model")
   - Copy the generated API key immediately (you won't be able to see it again)

3. **Add Credits**
   - Go to [Credits](https://openrouter.ai/credits) page
   - Add credits to your account (OpenRouter uses a pay-as-you-go model)
   - The model `google/gemini-2.5-flash-lite-preview-09-2025` is relatively affordable

4. **Configure in ViMax**
   - Open `configs/video.yaml`
   - Paste your API key in:
     ```yaml
     chat_model:
       init_args:
         api_key: sk-or-v1-xxxxxxxxxxxxx  # Your OpenRouter API key here
     ```

### Pricing:
- OpenRouter charges per token based on the model you use
- Check current pricing at [openrouter.ai/models](https://openrouter.ai/models)
- Gemini 2.5 Flash Lite is typically very cost-effective

---

## 2. Google AI Studio API Key (Image Generation)

### What it's used for:
- Generating character images
- Creating scene images
- Reference image generation
- Uses Google's Gemini Image API (`gemini-2.5-flash-image`)

### How to get it:

1. **Visit Google AI Studio**
   - Go to [https://aistudio.google.com/](https://aistudio.google.com/)
   - Sign in with your Google account

2. **Get API Key**
   - Click on **"Get API Key"** in the left sidebar
   - If you don't have a project, click "Create API Key in new project"
   - Or select an existing Google Cloud project
   - Copy the generated API key

3. **Enable Required APIs** (if needed)
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Navigate to "APIs & Services" > "Library"
   - Search for "Generative Language API" and enable it
   - Search for "Gemini API" and enable it

4. **Configure in ViMax**
   - Open `configs/video.yaml`
   - Paste your API key in:
     ```yaml
     image_generator:
       init_args:
         api_key: AIzaSyxxxxxxxxxxxxx  # Your Google AI Studio API key here
     ```

### Pricing:
- Google AI Studio offers a free tier with generous limits
- Check current pricing at [ai.google.dev/pricing](https://ai.google.dev/pricing)
- Image generation may have usage quotas

---

## 3. Google AI Studio API Key (Video Generation)

### What it's used for:
- Generating videos from images
- Creating video clips from prompts
- Uses Google's Veo Video API (`veo-3.1-generate-preview`)

### How to get it:

1. **Use Same or Create New Key**
   - You can use the **same Google AI Studio API key** from step 2
   - OR create a separate key for better tracking
   - Follow the same steps as in section 2

2. **Enable Video Generation API** (if needed)
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Navigate to "APIs & Services" > "Library"
   - Search for "Video Generation API" or "Veo API" and enable it
   - Note: Veo may require special access or be in preview

3. **Configure in ViMax**
   - Open `configs/video.yaml`
   - Paste your API key in:
     ```yaml
     video_generator:
       init_args:
         api_key: AIzaSyxxxxxxxxxxxxx  # Your Google AI Studio API key here
     ```

### Pricing:
- Veo video generation may have different pricing than image generation
- Check current pricing and availability at [ai.google.dev](https://ai.google.dev/)
- Video generation is typically more expensive than image generation

---

## Quick Setup Checklist

- [ ] Created OpenRouter account and added credits
- [ ] Generated OpenRouter API key
- [ ] Created Google account (if needed)
- [ ] Generated Google AI Studio API key(s)
- [ ] Enabled required Google Cloud APIs
- [ ] Updated `configs/video.yaml` with all three API keys
- [ ] Tested the configuration by running `main_video.py`

---

## Security Best Practices

1. **Never commit API keys to Git**
   - The `.gitignore` should exclude config files with keys
   - Use environment variables or secure secret management for production

2. **Use separate keys for different environments**
   - Development, staging, and production should have different keys
   - This allows you to revoke access without affecting other environments

3. **Monitor usage**
   - Regularly check your API usage and billing
   - Set up alerts for unexpected usage spikes

4. **Rotate keys periodically**
   - Generate new keys and update your config
   - Revoke old keys that are no longer needed

---

## Troubleshooting

### "Invalid API Key" Error
- Verify the API key is copied correctly (no extra spaces)
- Check if the API key has expired or been revoked
- Ensure you have sufficient credits/quota

### "Rate Limit Exceeded" Error
- Check the rate limits in `configs/video.yaml`
- Adjust `max_requests_per_minute` and `max_requests_per_day` values
- Consider upgrading your API plan

### "API Not Enabled" Error (Google)
- Go to Google Cloud Console
- Enable the required APIs (Generative Language API, Gemini API, etc.)
- Wait a few minutes for changes to propagate

### "Model Not Available" Error
- Check if the model name is correct
- Verify the model is available in your region
- Some models may require special access or be in preview

---

## Additional Resources

- [OpenRouter Documentation](https://openrouter.ai/docs)
- [Google AI Studio Documentation](https://ai.google.dev/docs)
- [Google Cloud Console](https://console.cloud.google.com/)
- [ViMax GitHub Issues](https://github.com/HKUDS/ViMax/issues) - For ViMax-specific questions

---

## Need Help?

If you encounter issues:
1. Check the troubleshooting section above
2. Review the API provider's documentation
3. Check ViMax GitHub issues and discussions
4. Verify your configuration matches the examples in the README
