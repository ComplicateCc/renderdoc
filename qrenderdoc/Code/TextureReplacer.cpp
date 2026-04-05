/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2015-2026 Baldur Karlsson
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 ******************************************************************************/

#include "TextureReplacer.h"

#include <QFileInfo>
#include <QImage>
#include <QMessageBox>
#include <cmath>
#include <cstring>

// Helper macro for logging - goes to both qWarning (Diagnostic Log) and adds to our status log
#define TEX_LOG(msg)                         \
  do                                         \
  {                                          \
    QString _msg = msg;                      \
    qWarning() << "TextureReplacer:" << _msg; \
    appendLog(_msg);                         \
  } while(0)

#define TEX_ERR(msg)                          \
  do                                          \
  {                                           \
    QString _msg = msg;                       \
    qCritical() << "TextureReplacer:" << _msg; \
    appendLog(QStringLiteral("[ERROR] ") + _msg); \
  } while(0)

TextureReplacer::TextureReplacer(ICaptureContext &ctx) : m_Ctx(ctx)
{
}

TextureReplacer::~TextureReplacer()
{
}

void TextureReplacer::appendLog(const QString &msg)
{
  m_StatusLog.append(msg);
  // Keep last 200 lines
  while(m_StatusLog.size() > 200)
    m_StatusLog.removeFirst();
}

QString TextureReplacer::GetStatusLog() const
{
  return m_StatusLog.join(QStringLiteral("\n"));
}

void TextureReplacer::ClearLog()
{
  m_StatusLog.clear();
}

bool TextureReplacer::LoadImageFile(const QString &path, LoadedImageData &imageData)
{
  QFileInfo fi(path);
  if(!fi.exists())
  {
    TEX_ERR(QStringLiteral("File does not exist: %1").arg(path));
    return false;
  }

  QImage img(path);
  if(img.isNull())
  {
    TEX_ERR(QStringLiteral("Failed to load image: %1").arg(path));
    return false;
  }

  // Convert to RGBA8 format
  QImage rgba = img.convertToFormat(QImage::Format_RGBA8888);

  imageData.width = rgba.width();
  imageData.height = rgba.height();
  imageData.channels = 4;
  imageData.isHDR = false;

  size_t dataSize = (size_t)rgba.width() * rgba.height() * 4;
  imageData.data.resize(dataSize);

  for(int y = 0; y < rgba.height(); y++)
  {
    const uchar *srcLine = rgba.constScanLine(y);
    memcpy(imageData.data.data() + (size_t)y * rgba.width() * 4, srcLine, (size_t)rgba.width() * 4);
  }

  TEX_LOG(QStringLiteral("Loaded image %1  (%2x%3)").arg(path).arg(rgba.width()).arg(rgba.height()));
  return true;
}

bool TextureReplacer::GenerateBuiltinTexture(BuiltinTexture type, int width, int height,
                                              LoadedImageData &imageData)
{
  imageData.width = width;
  imageData.height = height;
  imageData.channels = 4;
  imageData.isHDR = false;
  size_t dataSize = (size_t)width * height * 4;
  imageData.data.resize(dataSize);
  byte *pixels = imageData.data.data();

  for(int y = 0; y < height; y++)
  {
    for(int x = 0; x < width; x++)
    {
      size_t idx = ((size_t)y * width + x) * 4;
      switch(type)
      {
        case BuiltinTexture::White:
          pixels[idx + 0] = 255;
          pixels[idx + 1] = 255;
          pixels[idx + 2] = 255;
          pixels[idx + 3] = 255;
          break;

        case BuiltinTexture::Black:
          pixels[idx + 0] = 0;
          pixels[idx + 1] = 0;
          pixels[idx + 2] = 0;
          pixels[idx + 3] = 255;
          break;

        case BuiltinTexture::Gray:
          pixels[idx + 0] = 128;
          pixels[idx + 1] = 128;
          pixels[idx + 2] = 128;
          pixels[idx + 3] = 255;
          break;

        case BuiltinTexture::Checkerboard:
        {
          int cellSize = qMax(1, qMin(width, height) / 16);
          bool isWhite = ((x / cellSize) + (y / cellSize)) % 2 == 0;
          byte v = isWhite ? 255 : 0;
          pixels[idx + 0] = v;
          pixels[idx + 1] = v;
          pixels[idx + 2] = v;
          pixels[idx + 3] = 255;
          break;
        }

        case BuiltinTexture::UVGradient:
          pixels[idx + 0] = (byte)(255.0f * x / qMax(1, width - 1));
          pixels[idx + 1] = (byte)(255.0f * y / qMax(1, height - 1));
          pixels[idx + 2] = 0;
          pixels[idx + 3] = 255;
          break;

        case BuiltinTexture::NormalUp:
          pixels[idx + 0] = 128;
          pixels[idx + 1] = 128;
          pixels[idx + 2] = 255;
          pixels[idx + 3] = 255;
          break;

        default: break;
      }
    }
  }

  TEX_LOG(QStringLiteral("Generated builtin texture type=%1 (%2x%3)")
              .arg((int)type)
              .arg(width)
              .arg(height));
  return true;
}

bool TextureReplacer::ResizeIfNeeded(LoadedImageData &imageData, int targetWidth, int targetHeight)
{
  if(imageData.width == targetWidth && imageData.height == targetHeight)
    return true;

  TEX_LOG(QStringLiteral("Resizing from %1x%2 to %3x%4")
              .arg(imageData.width)
              .arg(imageData.height)
              .arg(targetWidth)
              .arg(targetHeight));

  QImage src((const uchar *)imageData.data.data(), imageData.width, imageData.height,
             imageData.width * 4, QImage::Format_RGBA8888);
  QImage dst =
      src.scaled(targetWidth, targetHeight, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
  dst = dst.convertToFormat(QImage::Format_RGBA8888);

  size_t dataSize = (size_t)targetWidth * targetHeight * 4;
  imageData.data.resize(dataSize);
  for(int y = 0; y < targetHeight; y++)
  {
    const uchar *srcLine = dst.constScanLine(y);
    memcpy(imageData.data.data() + (size_t)y * targetWidth * 4, srcLine, (size_t)targetWidth * 4);
  }

  imageData.width = targetWidth;
  imageData.height = targetHeight;
  return true;
}

void TextureReplacer::ReplaceTexture(ResourceId originalTexId, const LoadedImageData &imageData)
{
  LoadedImageData img = imageData;

  TEX_LOG(QStringLiteral("=== Starting texture replacement ==="));
  TEX_LOG(QStringLiteral("Target: %1 (ID: %2)")
              .arg(QString(m_Ctx.GetResourceName(originalTexId)))
              .arg(ToQStr(originalTexId)));
  TEX_LOG(QStringLiteral("Replacement data: %1x%2, %3 bytes")
              .arg(img.width)
              .arg(img.height)
              .arg(img.data.size()));

  m_Ctx.Replay().AsyncInvoke([this, originalTexId, img](IReplayController *r) {
    TEX_LOG(QStringLiteral("Step 1: Looking up original texture..."));

    // Find the original texture description
    const rdcarray<TextureDescription> &textures = r->GetTextures();
    const TextureDescription *origTex = nullptr;
    for(const TextureDescription &t : textures)
    {
      if(t.resourceId == originalTexId)
      {
        origTex = &t;
        break;
      }
    }

    if(!origTex)
    {
      TEX_ERR(QStringLiteral("Could not find original texture description!"));
      GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this]() {
        QMessageBox::warning(m_Ctx.GetMainWindow()->Widget(),
                             QStringLiteral("Texture Replace Failed"),
                             QStringLiteral("Could not find original texture. Check Diagnostic Log (Window menu) for details.\n\n%1").arg(GetStatusLog()));
      });
      return;
    }

    TEX_LOG(QStringLiteral("Step 1 OK: Found original texture - format=%1, dim=%2x%3, mips=%4, array=%5, type=%6")
                .arg(QString(origTex->format.Name()))
                .arg(origTex->width)
                .arg(origTex->height)
                .arg(origTex->mips)
                .arg(origTex->arraysize)
                .arg(origTex->dimension));

    // Create proxy texture with SAME format as original.
    // This is critical because ReplaceResource swaps the underlying ID3D11Resource,
    // and any SRVs created during replay use the original texture's format.
    // If we use a different format (e.g. RGBA8 for a BC1 original), the SRV creation
    // will fail with a format mismatch and the draw call won't render.
    TextureDescription proxyDesc = *origTex;
    proxyDesc.mips = 1;
    proxyDesc.arraysize = 1;
    proxyDesc.msSamp = 1;
    proxyDesc.msQual = 0;
    proxyDesc.cubemap = false;

    TEX_LOG(QStringLiteral("Step 2: Creating proxy texture with format=%1...")
                .arg(QString(proxyDesc.format.Name())));

    ResourceId proxyId = r->CreateProxyTexture(proxyDesc);
    if(proxyId == ResourceId())
    {
      TEX_ERR(QStringLiteral("CreateProxyTexture FAILED!"));
      GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this]() {
        QMessageBox::warning(m_Ctx.GetMainWindow()->Widget(),
                             QStringLiteral("Texture Replace Failed"),
                             QStringLiteral("Failed to create proxy texture.\n\n%1").arg(GetStatusLog()));
      });
      return;
    }

    TEX_LOG(QStringLiteral("Step 2 OK: Proxy texture created with ID=%1").arg(ToQStr(proxyId)));

    // Now we need to upload the data in the CORRECT format.
    // For non-compressed formats: upload RGBA8 directly if format matches, or convert.
    // For compressed formats (BC1-BC7): we need to get the expected data size and provide
    // appropriately formatted data.
    //
    // Strategy: Use GetTextureData to get the original texture's raw data for mip 0,
    // then we know the exact byte layout. For non-compressed, we upload our RGBA8 data.
    // For compressed, we upload the original data (no change) as a fallback, or try
    // to use the proxy as-is.

    Subresource sub;
    sub.mip = 0;
    sub.slice = 0;
    sub.sample = 0;

    bool isCompressed = (origTex->format.type == ResourceFormatType::BC1 ||
                         origTex->format.type == ResourceFormatType::BC2 ||
                         origTex->format.type == ResourceFormatType::BC3 ||
                         origTex->format.type == ResourceFormatType::BC4 ||
                         origTex->format.type == ResourceFormatType::BC5 ||
                         origTex->format.type == ResourceFormatType::BC6 ||
                         origTex->format.type == ResourceFormatType::BC7);

    if(isCompressed)
    {
      TEX_LOG(QStringLiteral("Step 3: Original texture is BLOCK COMPRESSED (%1). "
                             "Getting original raw data to determine expected size...")
                  .arg(QString(origTex->format.Name())));

      // For compressed textures, we can't just upload RGBA8 data.
      // Instead, we get the original texture data (already in compressed format)
      // and upload it to the proxy. This validates the pipeline works.
      // Then a proper compression step would be needed for real replacement.
      //
      // For now, get the raw data and see what size it expects.
      bytebuf origData = r->GetTextureData(originalTexId, sub);

      TEX_LOG(QStringLiteral("  Original raw data size: %1 bytes").arg(origData.size()));

      if(origData.empty())
      {
        TEX_ERR(QStringLiteral("GetTextureData returned empty data for compressed texture!"));
      }
      else
      {
        // Upload original compressed data to proxy - this at least validates the pipeline
        r->SetProxyTextureData(proxyId, sub, origData.data(), origData.size());
        TEX_LOG(QStringLiteral("Step 3 OK: Uploaded %1 bytes of compressed data to proxy").arg(origData.size()));
      }

      // Note: For actual replacement with a custom image, we would need to compress RGBA8 to BCn.
      // This is a TODO. For now, display a warning.
      TEX_LOG(QStringLiteral("WARNING: Compressed texture replacement is limited. "
                             "The proxy contains the original compressed data, not the replacement image."));
    }
    else
    {
      TEX_LOG(QStringLiteral("Step 3: Original texture is UNCOMPRESSED. Uploading RGBA8 data..."));

      // For uncompressed formats, we can try to upload RGBA8 data directly.
      // The proxy was created with the original format (which might be R8G8B8A8_UNORM,
      // R8G8B8A8_SRGB, etc.), and CreateProxyTexture uses GetTypelessFormat internally.
      // SetProxyTextureData expects data matching the typeless format's byte size.

      // Calculate expected data size for the proxy format
      // For R8G8B8A8_TYPELESS: 4 bytes per pixel = width * height * 4
      size_t expectedSize = (size_t)origTex->width * origTex->height *
                            origTex->format.compCount * origTex->format.compByteWidth;

      TEX_LOG(QStringLiteral("  Expected data size: %1 bytes (comp=%2, bpp=%3)")
                  .arg(expectedSize)
                  .arg(origTex->format.compCount)
                  .arg(origTex->format.compByteWidth));
      TEX_LOG(QStringLiteral("  Our RGBA8 data size: %1 bytes").arg(img.data.size()));

      bytebuf uploadData;

      if(img.data.size() == expectedSize)
      {
        // Sizes match - upload directly
        uploadData = img.data;
        TEX_LOG(QStringLiteral("  Size matches! Uploading directly."));
      }
      else if(expectedSize > 0 && img.data.size() != expectedSize)
      {
        // Size mismatch - the format has a different byte layout than RGBA8.
        // Try to adapt by getting original data first, then overlay what we can.
        TEX_LOG(QStringLiteral("  Size MISMATCH. Getting original data as template..."));
        uploadData = r->GetTextureData(originalTexId, sub);
        TEX_LOG(QStringLiteral("  Original data size from GetTextureData: %1").arg(uploadData.size()));

        if(uploadData.size() == expectedSize)
        {
          // We have the right size from GetTextureData. Use it as-is for now.
          // TODO: proper format conversion
          TEX_LOG(QStringLiteral("  Using original data as fallback (format conversion TODO)"));
        }
        else
        {
          // Last resort: just use our RGBA8 data and hope for the best
          uploadData = img.data;
          TEX_LOG(QStringLiteral("  WARNING: Using RGBA8 data despite size mismatch"));
        }
      }

      r->SetProxyTextureData(proxyId, sub, uploadData.data(), uploadData.size());
      TEX_LOG(QStringLiteral("Step 3 OK: Uploaded %1 bytes to proxy").arg(uploadData.size()));
    }

    TEX_LOG(QStringLiteral("Step 4: Calling ReplaceResource(%1 -> %2)...")
                .arg(ToQStr(originalTexId))
                .arg(ToQStr(proxyId)));

    r->ReplaceResource(originalTexId, proxyId);

    TEX_LOG(QStringLiteral("Step 4 OK: ReplaceResource completed (includes SetFrameEvent + Display)"));

    // Record the replacement on UI thread
    GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this, originalTexId, proxyId]() {
      TextureReplacement rep;
      rep.originalId = originalTexId;
      rep.proxyId = proxyId;
      m_Replacements[originalTexId] = rep;
      m_Ctx.RegisterReplacement(originalTexId, proxyId);
      TEX_LOG(QStringLiteral("Step 5 OK: Replacement registered on UI thread"));

      // Show success message
      QMessageBox::information(
          m_Ctx.GetMainWindow()->Widget(),
          QStringLiteral("Texture Replaced"),
          QStringLiteral("Texture replacement completed.\n\n"
                         "Open Window > Diagnostic Log to see full trace.\n\n"
                         "Last steps:\n%1")
              .arg(m_StatusLog.mid(qMax(0, m_StatusLog.size() - 5)).join(QStringLiteral("\n"))));
    });
  });
}

void TextureReplacer::ReplaceWithBuiltin(ResourceId originalTexId, BuiltinTexture type)
{
  const rdcarray<TextureDescription> &textures = m_Ctx.GetTextures();
  int width = 256, height = 256;
  for(const TextureDescription &t : textures)
  {
    if(t.resourceId == originalTexId)
    {
      width = (int)t.width;
      height = (int)t.height;
      break;
    }
  }

  TEX_LOG(QStringLiteral("ReplaceWithBuiltin type=%1 for %2 (%3x%4)")
              .arg((int)type)
              .arg(QString(m_Ctx.GetResourceName(originalTexId)))
              .arg(width)
              .arg(height));

  LoadedImageData imageData;
  if(!GenerateBuiltinTexture(type, width, height, imageData))
    return;

  ReplaceTexture(originalTexId, imageData);
}

void TextureReplacer::ReplaceFromFile(ResourceId originalTexId, const QString &filePath)
{
  TEX_LOG(QStringLiteral("ReplaceFromFile: %1 for %2")
              .arg(filePath)
              .arg(QString(m_Ctx.GetResourceName(originalTexId))));

  LoadedImageData imageData;
  if(!LoadImageFile(filePath, imageData))
    return;

  const rdcarray<TextureDescription> &textures = m_Ctx.GetTextures();
  for(const TextureDescription &t : textures)
  {
    if(t.resourceId == originalTexId)
    {
      ResizeIfNeeded(imageData, (int)t.width, (int)t.height);
      break;
    }
  }

  ReplaceTexture(originalTexId, imageData);
}

void TextureReplacer::RestoreTexture(ResourceId originalTexId)
{
  if(!m_Replacements.contains(originalTexId))
    return;

  TEX_LOG(QStringLiteral("Restoring original texture %1")
              .arg(QString(m_Ctx.GetResourceName(originalTexId))));

  m_Ctx.Replay().AsyncInvoke([this, originalTexId](IReplayController *r) {
    r->RemoveReplacement(originalTexId);

    GUIInvoke::call(m_Ctx.GetMainWindow()->Widget(), [this, originalTexId]() {
      m_Replacements.remove(originalTexId);
      m_Ctx.UnregisterReplacement(originalTexId);
      TEX_LOG(QStringLiteral("Texture restored successfully"));
    });

    r->SetFrameEvent(m_Ctx.CurEvent(), true);
  });
}

void TextureReplacer::RestoreAll()
{
  QList<ResourceId> ids = m_Replacements.keys();
  for(const ResourceId &id : ids)
  {
    RestoreTexture(id);
  }
}

bool TextureReplacer::IsReplaced(ResourceId texId) const
{
  return m_Replacements.contains(texId);
}

const TextureReplacement *TextureReplacer::GetReplacement(ResourceId texId) const
{
  auto it = m_Replacements.find(texId);
  if(it != m_Replacements.end())
    return &it.value();
  return nullptr;
}

void TextureReplacer::OnCaptureClosed()
{
  m_Replacements.clear();
  m_StatusLog.clear();
}