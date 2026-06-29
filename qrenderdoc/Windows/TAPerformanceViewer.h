/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Baldur Karlsson
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
#include <QSortFilterProxyModel>
#include <QTreeView>
#include "Code/Interface/QRDInterface.h"

class QToolButton;

class TAPerformanceModel;
class TAPerformanceFilterModel;

class TAPerformanceViewer : public QFrame, public ICaptureViewer
{
public:
  explicit TAPerformanceViewer(ICaptureContext &ctx, QWidget *parent = 0);
  ~TAPerformanceViewer();

  QWidget *Widget() { return this; }

  void OnCaptureLoaded() override;
  void OnCaptureClosed() override;
  void OnSelectedEventChanged(uint32_t eventId) override {}
  void OnEventChanged(uint32_t eventId) override;

private:
  void Refresh();
  void CaptureCounters();
  void ExportCSV();
  void SyncToEvent(uint32_t eventId);

  ICaptureContext &m_Ctx;
  TAPerformanceModel *m_Model = NULL;
  TAPerformanceFilterModel *m_Filter = NULL;
  QTreeView *m_Tree = NULL;
  QToolButton *m_Refresh = NULL;
  QToolButton *m_CaptureCounters = NULL;
  QToolButton *m_Sync = NULL;
  QToolButton *m_HideEmptyDraws = NULL;
  QToolButton *m_Expand = NULL;
  QToolButton *m_Collapse = NULL;
  QToolButton *m_SaveCSV = NULL;
  QList<GPUCounter> m_SelectedCounters;
  rdcarray<CounterDescription> m_CounterDescriptions;
  rdcarray<CounterResult> m_CounterResults;
};
