/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2024-2026 Baldur Karlsson
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

#pragma once

#include <QFrame>
#include <QMap>
#include "Code/Interface/QRDInterface.h"

namespace Ui
{
class CBufferEditor;
}

class QStandardItemModel;
class QStandardItem;

struct CBufferEdit
{
  ShaderStage stage;
  uint32_t slot;
  uint32_t arrayIdx;
  ResourceId bufId;
  bytebuf originalData;
  bytebuf modifiedData;
  bool dirty = false;
};

class CBufferEditor : public QFrame, public ICBufferEditor, public ICaptureViewer
{
  Q_OBJECT

public:
  explicit CBufferEditor(ICaptureContext &ctx, QWidget *parent = 0);
  ~CBufferEditor();

  // ICBufferEditor
  QWidget *Widget() override { return this; }

  // ICaptureViewer
  void OnCaptureLoaded() override;
  void OnCaptureClosed() override;
  void OnSelectedEventChanged(uint32_t eventId) override {}
  void OnEventChanged(uint32_t eventId) override;

private slots:
  void on_applyButton_clicked();
  void on_resetButton_clicked();
  void on_cbufferTree_doubleClicked(const QModelIndex &index);
  void on_cbufferTree_customContextMenuRequested(const QPoint &pos);

private:
  Ui::CBufferEditor *ui;
  ICaptureContext &m_Ctx;

  QStandardItemModel *m_Model = nullptr;
  uint32_t m_CurrentEventId = 0;

  // Track edits per (stage, slot, arrayIdx) key
  QMap<QString, CBufferEdit> m_Edits;

  void RefreshCBuffers();
  void PopulateStage(ShaderStage stage, const ShaderReflection *refl);
  void ApplyEdits();
  void ResetAll();
  void ResetVariable(const QModelIndex &index);
  void ClearAll();

  QString MakeEditKey(ShaderStage stage, uint32_t slot, uint32_t arrayIdx);
  void MarkModified(QStandardItem *item, bool modified);
};
