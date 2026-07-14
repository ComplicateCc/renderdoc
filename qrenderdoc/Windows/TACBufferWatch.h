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
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
 ******************************************************************************/

#pragma once

#include <QFrame>
#include <QTableWidget>
#include "Code/Interface/QRDInterface.h"

class QCheckBox;
class QComboBox;
class QSpinBox;
class QToolButton;
class TACBufferWatchGraph;

class TACBufferWatch : public QFrame, public ICaptureViewer
{
public:
  explicit TACBufferWatch(ICaptureContext &ctx, QWidget *parent = 0);
  ~TACBufferWatch();

  QWidget *Widget() { return this; }

  void OnCaptureLoaded() override;
  void OnCaptureClosed() override;
  void OnSelectedEventChanged(uint32_t eventId) override {}
  void OnEventChanged(uint32_t eventId) override;

public:
  struct WatchVariable
  {
    ShaderStage stage = ShaderStage::Vertex;
    uint32_t slot = 0;
    rdcstr path;
  };

  struct WatchSample
  {
    uint32_t eventId = 0;
    rdcstr actionName;
    ShaderStage stage = ShaderStage::Vertex;
    uint32_t slot = 0;
    rdcstr path;
    rdcstr value;
    bool changed = false;
  };

  void AddCurrentCBufferVariables();
  void Refresh();
  void ExportCSV();
  void PopulateWatchMenu();
  void GatherVariables(const rdcarray<ShaderVariable> &vars, const rdcstr &prefix,
                       rdcarray<WatchVariable> &out) const;
  void GatherSamplesForEvent(IReplayController *r, uint32_t eventId, const ActionDescription *action,
                             rdcarray<WatchSample> &out) const;
  void ApplySamples(const rdcarray<WatchSample> &samples);

  ICaptureContext &m_Ctx;
  QComboBox *m_WatchList = NULL;
  QSpinBox *m_MaxEvents = NULL;
  QCheckBox *m_ChangesOnly = NULL;
  QToolButton *m_AddCurrent = NULL;
  QToolButton *m_Refresh = NULL;
  QToolButton *m_Clear = NULL;
  QToolButton *m_Export = NULL;
  QTableWidget *m_Table = NULL;
  TACBufferWatchGraph *m_Graph = NULL;
  rdcarray<WatchVariable> m_Watches;
};
